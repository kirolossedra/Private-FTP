from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# Set up user credentials
authorizer = DummyAuthorizer()
authorizer.add_user("user", "pass", ".", perm="elr")  # e=read, l=list, r=read

# FTP handler
handler = FTPHandler
handler.authorizer = authorizer

# Start server on default FTP port 21
server = FTPServer(("0.0.0.0", 2121), handler)
print("FTP server started on port 21. Serving ./download file")
server.serve_forever()

