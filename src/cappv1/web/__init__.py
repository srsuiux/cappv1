"""The local web UI: a standard-library HTTP server over src/cappv1/services.

No framework and no logic of its own. Each route calls a service and turns
the result (or a ServiceError) into JSON.
"""
