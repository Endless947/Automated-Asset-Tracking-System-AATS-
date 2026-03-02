import servicemanager
import win32event
import win32service
import win32serviceutil

from service_runner import AgentRuntime


class AATSAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "AATSAgentService"
    _svc_display_name_ = "AATS Student Agent Service"
    _svc_description_ = "Monitors configured USB/Bluetooth peripherals and reports status to the AATS server over MQTT."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._runtime = AgentRuntime()

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("AATSAgentService starting.")
        self._runtime.start()
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        self._runtime.stop()
        servicemanager.LogInfoMsg("AATSAgentService stopped.")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(AATSAgentService)

