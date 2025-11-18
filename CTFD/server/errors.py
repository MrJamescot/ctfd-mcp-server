class CTFdError(Exception):
    pass

class ForbiddenError(CTFdError):
    pass

class ServerDownError(CTFdError):
    pass
