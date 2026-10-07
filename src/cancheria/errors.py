class CancheriaError(Exception): pass
class ConfigurationError(CancheriaError): pass
class ReservationError(CancheriaError): pass
class PaymentError(CancheriaError): pass
class ChannelError(CancheriaError): pass
class AgentInvariantError(CancheriaError): pass
