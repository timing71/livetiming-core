from autobahn.twisted.wamp import ApplicationSession
from autobahn.wamp.types import PublishOptions, RegisterOptions
from livetiming.network import Channel, RPC, authenticatedService
from twisted.internet.defer import inlineCallbacks


def create_service_session(service):
    class ServiceSession(ApplicationSession):

        def _isAlive(self):
            return True

        @inlineCallbacks
        def onJoin(self, details):
            service.log.info("Session ready for service {}".format(service.uuid))
            service.set_publish(self.publish)

            register_opts = RegisterOptions(force_reregister=True)

            yield self.register(self._isAlive, RPC.LIVENESS_CHECK.format(service.uuid), register_opts)
            yield self.register(service._requestCurrentState, RPC.REQUEST_STATE.format(service.uuid), register_opts)
            yield self.register(service._requestCurrentAnalysisState, RPC.REQUEST_ANALYSIS_DATA.format(service.uuid), register_opts)
            yield self.subscribe(service.onControlMessage, Channel.CONTROL)
            self.log.info("Subscribed to control channel")
            yield service.publishManifest()
            self.log.info("Published init message")
            service._updateAndPublishRaceState()

        def onLeave(self, details):
            super(ServiceSession, self).onLeave(details)
            service.log.info("Left WAMP session: {details}", details=details)

        def onDisconnect(self):
            service.log.info("Disconnected from live timing service")
            service.set_publish(None)

    return authenticatedService(ServiceSession)
