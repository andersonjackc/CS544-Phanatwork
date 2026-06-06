import argparse
import asyncio
from aioquic.quic.configuration import QuicConfiguration
import phanatwork_client
import quic_engine
import phanatwork_server
import pdu

# mainly copied from echo.py example project
# modified to have more args 
# not fully completed as  some things will need to be refactored 
# as things are more fleshed out

def client_mode(args):
    server_address = args.server
    server_port = args.port
    cert_file = args.cert_file
    desired_role = role_from_string(args.role)
    scope = {
        "name": args.name,
        "team": args.team,
        "role": desired_role,
        "message": args.message,
    }
    
    config = quic_engine.build_client_quic_config(cert_file)
    asyncio.run(quic_engine.run_client(server_address, server_port, config, scope))
    
    
def server_mode(args):
    listen_address = args.listen
    listen_port = args.port
    cert_file = args.cert_file
    key_file = args.key_file
    
    server_config = quic_engine.build_server_quic_config(cert_file, key_file)
    asyncio.run(quic_engine.run_server(listen_address, listen_port, server_config))

def role_from_string(role_name):
    if role_name.lower() == "home":
        return pdu.ROLE_HOME
    if role_name.lower() == "away":
        return pdu.ROLE_AWAY
    return pdu.ROLE_NONE

def parse_args():
    parser = argparse.ArgumentParser(description='Phanatwork minimal example')
    subparsers = parser.add_subparsers(dest='mode', help='Mode to run the application in', required=True)
    
    client_parser = subparsers.add_parser('client')
    client_parser.add_argument('-s','--server', default='localhost', help='Host to connect to')   
    client_parser.add_argument('-p','--port', type=int, default=4433, help='Port to connect to')
    client_parser.add_argument('-c','--cert-file', default='./certs/quic_certificate.pem', help='Certificate file (for self signed certs)')
    client_parser.add_argument('-n','--name', default='Player', help='Client display name')
    client_parser.add_argument('-t','--team', default='Team', help='Team name')
    client_parser.add_argument('-r','--role', default='either', choices=['home','away','either'], help='Requested role')
    client_parser.add_argument('-m','--message', default='This is a Phanatwork test message', help='Text message to send after START')

    server_parser = subparsers.add_parser('server')
    server_parser.add_argument('-c','--cert-file', default='./certs/quic_certificate.pem', help='Certificate file (for self signed certs)')
    server_parser.add_argument('-k','--key-file', default='./certs/quic_private_key.pem', help='Key file (for self signed certs)')
    server_parser.add_argument('-l','--listen', default='localhost', help='Address to listen on')
    server_parser.add_argument('-p','--port', type=int, default=4433, help='Port to listen on')
       
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    if args.mode == 'client':
        client_mode(args)
    elif args.mode == 'server':
        server_mode(args)
    else:
        print('Invalid mode')

