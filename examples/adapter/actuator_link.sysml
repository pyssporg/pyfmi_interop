// An actuator link with an inbound command port and an outbound feedback port.
// The fixed-length array fields become one scalar FMI variable per element.
//
// Deployment-varying configuration is a parameter interface: the runtime binds
// its transport from these FMI parameters, so one build serves every endpoint.
// Structural facts (step size, serialization backend, role) stay build-time
// attributes and are deliberately not parameters.
package ActuatorLinkExample {
  private import ScalarValues::*;
  private import PysspCore::*;

  port def InteropDeployment :> ParameterInterface {
    attribute transport : String = "udp";
    attribute bind_address : String = "0.0.0.0:5000";
    attribute peer_address : String = "";
    attribute queue_depth : Integer = 8;
  }

  port def Command {
    attribute setpoint : Real;
    attribute mode : Integer;
    attribute enable : Boolean;
    attribute gains : Real[3];
  }

  port def Feedback {
    attribute position : Real;
    attribute status : Integer;
    attribute healthy : Boolean;
    attribute samples : Real[2];
  }

  part def ActuatorLink {
    in port command : Command;
    out port feedback : Feedback;
    in port parameters : InteropDeployment;
  }

  // A partial set for the bench deployment.  Bound beside the composition; a
  // master can still override any member through its parameter value reference.
  attribute def BenchDefaults :> ParameterSet {
    attribute transport = "loopback";
  }

  part def Root {
    part link : ActuatorLink;
    attribute bench : BenchDefaults;
    bind link.parameters = bench;
  }
}
