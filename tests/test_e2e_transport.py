"""End-to-end UDP exchange: one part definition, a sender and a receiver FMU.

The test drives two separately built adapter models as two processes: a sender
that publishes the scenario on its input value references and a receiver that
applies the frame to its output value references.  The receiver view flips the
authored causality so the same interface is consumed; name, value references,
data types, step size and therefore the wire model id stay identical.

A raw ``payload_format`` mismatch is injected from Python and must be dropped:
the receiver keeps the values it had after the good exchange.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from dataclasses import replace
from pathlib import Path

import pytest

from pyfmi_interop import native, wire
from pyfmi_interop.builder import build_model
from pyfmi_interop.codegen import generate_model
from pyfmi_interop.ir import Direction
from pyfmi_interop.serialization import packed

pytestmark = [pytest.mark.cpp, pytest.mark.system]

_CMAKE = shutil.which("cmake")
_CXX = shutil.which(os.environ.get("CXX", "c++")) or shutil.which("g++") or shutil.which("clang++")
_PROTOC = shutil.which("protoc")

_FIXTURE = textwrap.dedent(
    """\
    package Exchange {
      private import ScalarValues::*;
      private import PysspCore::*;

      port def Command {
        attribute demand : Real;
        attribute mode : Integer;
        attribute enabled : Boolean;
      }

      port def Status {
        attribute actual : Real;
        attribute code : Integer;
        attribute ok : Boolean;
      }

      part def Exchange {
        in port command : Command;
        out port status : Status;
      }

      part def Root {
        part exchange : Exchange;
      }
    }
    """
)

_RUNNER = textwrap.dedent(
    r"""
    #include "fmi2Functions.h"

    #include <chrono>
    #include <cstdarg>
    #include <cstdio>
    #include <cstdlib>
    #include <cstring>
    #include <fstream>
    #include <string>
    #include <thread>
    #include <vector>

    namespace {

    struct RealArg { fmi2ValueReference vr; fmi2Real value; };
    struct IntArg { fmi2ValueReference vr; fmi2Integer value; };
    struct BoolArg { fmi2ValueReference vr; fmi2Boolean value; };

    void logger(fmi2ComponentEnvironment, fmi2String instance, fmi2Status,
                fmi2String category, fmi2String message, ...) {
        std::fprintf(stderr, "[%s] %s: ", instance ? instance : "?",
                     category ? category : "");
        va_list args;
        va_start(args, message);
        std::vfprintf(stderr, message, args);
        va_end(args);
        std::fprintf(stderr, "\n");
    }

    [[noreturn]] void fail(const char* what) {
        std::fprintf(stderr, "runner error: %s\n", what);
        std::exit(2);
    }

    void expect(fmi2Status status, const char* what) {
        if (status != fmi2OK && status != fmi2Warning) {
            fail(what);
        }
    }

    void* allocate_memory(std::size_t count, std::size_t size) {
        return std::malloc(count * size);
    }

    void free_memory(void* pointer) { std::free(pointer); }

    bool parse_vr(const char* text, fmi2ValueReference& vr, double& value) {
        char* end = nullptr;
        vr = static_cast<fmi2ValueReference>(std::strtoul(text, &end, 10));
        if (end == text || *end != '=') {
            return false;
        }
        value = std::strtod(end + 1, &end);
        return *end == '\0';
    }

    bool exists(const std::string& path) {
        std::ifstream stream(path);
        return stream.good();
    }

    void wait_for(const std::string& path) {
        for (int attempt = 0; attempt < 4000; ++attempt) {
            if (exists(path)) {
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        fail("timed out waiting for a marker file");
    }

    }  // namespace

    int main(int argc, char** argv) {
        unsigned steps = 0;
        unsigned steps2 = 0;
        double step_size = 0.001;
        std::string ready_file;
        std::string await_before;
        std::string phase1_file;
        std::string await_after;
        std::vector<RealArg> set_real;
        std::vector<IntArg> set_int;
        std::vector<BoolArg> set_bool;
        std::vector<RealArg> get_real;
        std::vector<IntArg> get_int;
        std::vector<BoolArg> get_bool;

        for (int index = 1; index < argc; ++index) {
            const std::string arg = argv[index];
            auto next = [&](const char* name) -> const char* {
                if (index + 1 >= argc) {
                    fail(name);
                }
                return argv[++index];
            };
            if (arg == "--steps") {
                steps = static_cast<unsigned>(std::strtoul(next("--steps"), nullptr, 10));
            } else if (arg == "--steps2") {
                steps2 = static_cast<unsigned>(std::strtoul(next("--steps2"), nullptr, 10));
            } else if (arg == "--step-size") {
                step_size = std::strtod(next("--step-size"), nullptr);
            } else if (arg == "--ready-file") {
                ready_file = next("--ready-file");
            } else if (arg == "--await-before") {
                await_before = next("--await-before");
            } else if (arg == "--phase1-file") {
                phase1_file = next("--phase1-file");
            } else if (arg == "--await-after") {
                await_after = next("--await-after");
            } else if (arg == "--set-real") {
                RealArg item{};
                double value = 0.0;
                if (!parse_vr(next("--set-real"), item.vr, value)) {
                    fail("bad --set-real");
                }
                item.value = value;
                set_real.push_back(item);
            } else if (arg == "--set-int") {
                IntArg item{};
                double value = 0.0;
                if (!parse_vr(next("--set-int"), item.vr, value)) {
                    fail("bad --set-int");
                }
                item.value = static_cast<fmi2Integer>(value);
                set_int.push_back(item);
            } else if (arg == "--set-bool") {
                BoolArg item{};
                double value = 0.0;
                if (!parse_vr(next("--set-bool"), item.vr, value)) {
                    fail("bad --set-bool");
                }
                item.value = value != 0.0 ? fmi2True : fmi2False;
                set_bool.push_back(item);
            } else if (arg == "--get-real") {
                RealArg item{};
                item.vr = static_cast<fmi2ValueReference>(
                    std::strtoul(next("--get-real"), nullptr, 10));
                get_real.push_back(item);
            } else if (arg == "--get-int") {
                IntArg item{};
                item.vr = static_cast<fmi2ValueReference>(
                    std::strtoul(next("--get-int"), nullptr, 10));
                get_int.push_back(item);
            } else if (arg == "--get-bool") {
                BoolArg item{};
                item.vr = static_cast<fmi2ValueReference>(
                    std::strtoul(next("--get-bool"), nullptr, 10));
                get_bool.push_back(item);
            } else {
                fail("unknown argument");
            }
        }

        fmi2CallbackFunctions callbacks{};
        callbacks.logger = logger;
        callbacks.allocateMemory = allocate_memory;
        callbacks.freeMemory = free_memory;
        callbacks.stepFinished = nullptr;

        fmi2Component component = fmi2Instantiate(
            "runner", fmi2CoSimulation, fmi2TypesPlatform, "file:///tmp",
            &callbacks, fmi2False, fmi2True);
        if (component == nullptr) {
            fail("fmi2Instantiate failed");
        }
        if (!ready_file.empty()) {
            std::ofstream(ready_file) << "ready\n";
        }

        expect(fmi2SetupExperiment(component, fmi2False, 0.0, 0.0, fmi2False, 0.0),
               "fmi2SetupExperiment");
        expect(fmi2EnterInitializationMode(component), "fmi2EnterInitializationMode");
        if (!await_before.empty()) {
            wait_for(await_before);
        }
        for (const RealArg& item : set_real) {
            fmi2ValueReference vr = item.vr;
            expect(fmi2SetReal(component, &vr, 1, &item.value), "fmi2SetReal");
        }
        for (const IntArg& item : set_int) {
            fmi2ValueReference vr = item.vr;
            expect(fmi2SetInteger(component, &vr, 1, &item.value), "fmi2SetInteger");
        }
        for (const BoolArg& item : set_bool) {
            fmi2ValueReference vr = item.vr;
            expect(fmi2SetBoolean(component, &vr, 1, &item.value), "fmi2SetBoolean");
        }
        expect(fmi2ExitInitializationMode(component), "fmi2ExitInitializationMode");

        double time_s = 0.0;
        auto run = [&](unsigned count) {
            for (unsigned index = 0; index < count; ++index) {
                expect(fmi2DoStep(component, time_s, step_size, fmi2True), "fmi2DoStep");
                time_s += step_size;
            }
        };
        auto emit = [&](const char* phase) {
            for (const RealArg& item : get_real) {
                fmi2ValueReference vr = item.vr;
                fmi2Real value = 0.0;
                expect(fmi2GetReal(component, &vr, 1, &value), "fmi2GetReal");
                std::printf("%s real %u %.17g\n", phase, vr, value);
            }
            for (const IntArg& item : get_int) {
                fmi2ValueReference vr = item.vr;
                fmi2Integer value = 0;
                expect(fmi2GetInteger(component, &vr, 1, &value), "fmi2GetInteger");
                std::printf("%s integer %u %d\n", phase, vr, static_cast<int>(value));
            }
            for (const BoolArg& item : get_bool) {
                fmi2ValueReference vr = item.vr;
                fmi2Boolean value = fmi2False;
                expect(fmi2GetBoolean(component, &vr, 1, &value), "fmi2GetBoolean");
                std::printf("%s boolean %u %d\n", phase, vr,
                            value == fmi2True ? 1 : 0);
            }
            std::fflush(stdout);
        };

        run(steps);
        emit("P1");
        if (!phase1_file.empty()) {
            std::ofstream(phase1_file) << "phase1\n";
        }
        if (steps2 > 0) {
            if (!await_after.empty()) {
                wait_for(await_after);
            }
            run(steps2);
            emit("P2");
        }

        fmi2Terminate(component);
        fmi2FreeInstance(component);
        return 0;
    }
    """
)


def _skip_reason() -> str | None:
    if _CMAKE is None:
        return "cmake is not available"
    if _CXX is None:
        return "a C++ compiler is not available"
    if sys.platform == "win32":
        return "the end-to-end runner is POSIX-only"
    if not native.bundled_library_path().is_file() and not native.default_runtime_library_path(
        Path(__file__).resolve().parents[1]
    ).is_file():
        return "the native runtime has not been built"
    if not native.bundled_transport_library_path().is_file() and not any(
        path.is_file()
        for path in native.transport_search_paths(Path(__file__).resolve().parents[1])
    ):
        return "the native transport has not been built"
    return None


_SKIP = _skip_reason()


@pytest.fixture(scope="module")
def source_model(tmp_path_factory):
    pytest.importorskip("pycps_sysml2")
    pytest.importorskip("pyfmi_sysml2")
    from pyfmi_interop import sysml

    source = tmp_path_factory.mktemp("sysml") / "exchange.sysml"
    source.write_text(_FIXTURE, encoding="utf-8")
    return sysml.load_model(source, name="ExchangeModel")


def _receiver_view(model):
    """Same interface, consumed: every authored direction is flipped."""

    def flip(direction: Direction) -> Direction:
        if direction is Direction.INPUT:
            return Direction.OUTPUT
        if direction is Direction.OUTPUT:
            return Direction.INPUT
        return direction

    return replace(
        model,
        signals=tuple(
            replace(signal, direction=flip(signal.direction))
            for signal in model.signals
        ),
        role=None,
        serialization=None,
    )


def _wire_signals(model_dir: Path) -> tuple[dict, list[dict]]:
    document = json.loads((model_dir / "wire.json").read_text(encoding="utf-8"))
    return document, document["signals"]


def _scenario(signals: list[dict], direction: str) -> dict[str, object]:
    values: dict[str, object] = {}
    for index, signal in enumerate(
        sorted((item for item in signals if item["direction"] == direction),
               key=lambda item: item["id"])
    ):
        if signal["data_type"] == "real":
            values[signal["name"]] = 12.5 + index
        elif signal["data_type"] == "integer":
            values[signal["name"]] = 7 + index
        elif signal["data_type"] == "boolean":
            values[signal["name"]] = 1
        else:  # pragma: no cover - the fixture has no string fields
            values[signal["name"]] = f"value-{index}"
    return values


def _setter_args(signals: list[dict], values: dict[str, object]) -> list[str]:
    args: list[str] = []
    for signal in signals:
        if signal["name"] not in values:
            continue
        flag = {
            "real": "--set-real",
            "integer": "--set-int",
            "boolean": "--set-bool",
            "string": "--set-real",
        }[signal["data_type"]]
        value = values[signal["name"]]
        args.extend([flag, f"{signal['id']}={value}"])
    return args


def _getter_args(signals: list[dict]) -> list[str]:
    args: list[str] = []
    for signal in signals:
        flag = {
            "real": "--get-real",
            "integer": "--get-int",
            "boolean": "--get-bool",
            "string": "--get-real",
        }[signal["data_type"]]
        args.extend([flag, str(signal["id"])])
    return args


def _parse(stdout: str) -> dict[str, dict[tuple[str, int], object]]:
    phases: dict[str, dict[tuple[str, int], object]] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[0] not in {"P1", "P2"}:
            continue
        phase, kind, vr, raw = parts
        key = (kind, int(vr))
        if kind == "real":
            phases.setdefault(phase, {})[key] = float(raw)
        elif kind == "integer":
            phases.setdefault(phase, {})[key] = int(raw)
        else:
            phases.setdefault(phase, {})[key] = bool(int(raw))
    return phases


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _build_model(model, directory: Path, role: str, serialization: str) -> Path:
    source = generate_model(model, directory, serialization=serialization, role=role)
    return build_model(source, directory / "build")


def _compile_runner(directory: Path, library: Path) -> Path:
    source = directory / "runner.cpp"
    source.write_text(_RUNNER, encoding="utf-8")
    executable = directory / "runner"
    headers = Path(__file__).resolve().parents[1] / "third_party" / "fmi2" / "headers"
    completed = subprocess.run(
        [
            _CXX,
            "-std=c++17",
            "-O0",
            str(source),
            str(library),
            "-I",
            str(headers),
            f"-Wl,-rpath,{library.parent}",
            "-pthread",
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return executable


def _start(command: list[str], env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for(path: Path, process: subprocess.Popen, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            out, err = process.communicate()
            raise AssertionError(f"process exited early:\n{out}\n{err}")
        time.sleep(0.005)
    process.kill()
    out, err = process.communicate()
    raise AssertionError(f"timed out waiting for {path}:\n{out}\n{err}")


def _run_exchange(model, tmp_path: Path, serialization: str) -> None:
    receiver_view = _receiver_view(model)
    sender_dir = tmp_path / f"sender_{serialization}"
    receiver_dir = tmp_path / f"receiver_{serialization}"
    sender_library = _build_model(model, sender_dir, "sender", serialization)
    receiver_library = _build_model(receiver_view, receiver_dir, "receiver", serialization)
    sender_runner = _compile_runner(sender_dir, sender_library)
    receiver_runner = _compile_runner(receiver_dir, receiver_library)

    sender_wire, sender_signals = _wire_signals(sender_dir)
    receiver_wire, receiver_signals = _wire_signals(receiver_dir)
    assert sender_wire["model_id"] == receiver_wire["model_id"]

    inputs = [item for item in sender_signals if item["direction"] == "input"]
    outputs = [item for item in receiver_signals if item["direction"] == "output"]
    assert [item["name"] for item in inputs] == [item["name"] for item in outputs]
    scenario = _scenario(sender_signals, "input")

    port = _free_udp_port()
    base_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYFMI_INTEROP_TRANSPORT", "PYFMI_INTEROP_TRANSPORT_ENDPOINT"}
    }

    ready = tmp_path / "ready"
    sender_done = tmp_path / "sender_done"
    phase1 = tmp_path / "phase1"
    poison_done = tmp_path / "poison_done"

    receiver_env = dict(base_env)
    receiver_env["PYFMI_INTEROP_TRANSPORT"] = f"udp://127.0.0.1:{port}"
    receiver_process = _start(
        [
            str(receiver_runner),
            "--ready-file",
            str(ready),
            "--await-before",
            str(sender_done),
            "--steps",
            "20",
            "--phase1-file",
            str(phase1),
            "--await-after",
            str(poison_done),
            "--steps2",
            "20",
            *_getter_args(outputs),
        ],
        receiver_env,
    )

    try:
        _wait_for(ready, receiver_process)

        sender_env = dict(base_env)
        sender_env["PYFMI_INTEROP_TRANSPORT"] = (
            f"udp://127.0.0.1:0?peer=127.0.0.1:{port}"
        )
        sender_process = _start(
            [str(sender_runner), "--steps", "20", *_setter_args(inputs, scenario)],
            sender_env,
        )
        sender_out, sender_err = sender_process.communicate(timeout=30)
        assert sender_process.returncode == 0, sender_out + sender_err

        sender_done.write_text("done\n", encoding="utf-8")
        _wait_for(phase1, receiver_process)

        # A valid frame for this model id, but tagged with the wrong payload
        # format: the receiver must reject it before decoding the payload.
        poison = wire.encode(
            receiver_view,
            packed.encode(receiver_view),
            instance=99,
            sequence=1,
            timestamp_ns=0,
            payload_format=wire.PayloadFormat.PROTOBUF,
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as poison_socket:
            for _ in range(5):
                poison_socket.sendto(poison, ("127.0.0.1", port))

        poison_done.write_text("done\n", encoding="utf-8")
        receiver_out, receiver_err = receiver_process.communicate(timeout=30)
        assert receiver_process.returncode == 0, receiver_out + receiver_err
    finally:
        if receiver_process.poll() is None:
            receiver_process.kill()
            receiver_process.communicate()

    phases = _parse(receiver_out)
    first = phases["P1"]
    second = phases["P2"]
    assert len(first) == len(outputs)

    for signal in outputs:
        key = (signal["data_type"], signal["id"])
        expected = scenario[signal["name"]]
        assert first[key] == expected, (
            signal["name"], first[key], expected, receiver_err)
        assert second[key] == first[key], (signal["name"], second[key], first[key])
        if signal["data_type"] == "real":
            assert first[key] == first[key], "the receiver produced a NaN"


@pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")
def test_part_definition_udp_exchange_packed(source_model, tmp_path):
    """One part definition, two processes, real UDP, packed payload."""

    _run_exchange(source_model, tmp_path, "packed")


@pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")
@pytest.mark.skipif(_PROTOC is None, reason="protoc is not available")
def test_part_definition_udp_exchange_protobuf(source_model, tmp_path):
    """The same exchange with the canonical protobuf payload backend."""

    _run_exchange(source_model, tmp_path, "protobuf")
