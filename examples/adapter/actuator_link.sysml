// An actuator link with an inbound command port and an outbound feedback port.
// The fixed-length array fields become one scalar FMI variable per element.
package ActuatorLinkExample {
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
  }

  part def Root {
    part link : ActuatorLink;
  }
}
