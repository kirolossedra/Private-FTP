from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# Set up user credentials
authorizer = DummyAuthorizer()
authorizer.add_user("user", "pass", ".", perm="elr")  # e=read, l=list, r=read

authorizer.add_user("user1", "pass", ".", perm="elr")
authorizer.add_user("user2", "pass", ".", perm="elr")
authorizer.add_user("user3", "pass", ".", perm="elr")
authorizer.add_user("user4", "pass", ".", perm="elr")
authorizer.add_user("user5", "pass", ".", perm="elr")
authorizer.add_user("user6", "pass", ".", perm="elr")
authorizer.add_user("user7", "pass", ".", perm="elr")
authorizer.add_user("user8", "pass", ".", perm="elr")
authorizer.add_user("user9", "pass", ".", perm="elr")
authorizer.add_user("user10", "pass", ".", perm="elr")
authorizer.add_user("user11", "pass", ".", perm="elr")
authorizer.add_user("user12", "pass", ".", perm="elr")
authorizer.add_user("user13", "pass", ".", perm="elr")
authorizer.add_user("user14", "pass", ".", perm="elr")



authorizer.add_user("user17", "pass", ".", perm="elr")  # e=read, l=list, r=read



authorizer.add_user("user18", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user19", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user20", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user21", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user22", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user23", "pass", ".", perm="elr")  # e=read, l=list, r=read
authorizer.add_user("user24", "pass", ".", perm="elr")  # e=read, l=list, r=read

# FTP handler
handler = FTPHandler
handler.authorizer = authorizer

# Start server on default FTP port 21
server = FTPServer(("0.0.0.0", 2121), handler)
print("FTP server started on port 21. Serving ./download file")
server.serve_forever()
