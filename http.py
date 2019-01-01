import socket
import sys
import errno
import os

class MyServer:
    def __init__(self, port, doc_root):
        self.port = port 
        self.server_address = "localhost"
        ip_port = (self.server_address, self.port)

        doc_path = doc_root
        if doc_path[len(doc_path) - 1] == '/':
            doc_path = doc_path[:len(doc_path)-1]

        if os.path.exists(doc_path):    #absolute path
            self.doc_root = doc_path
        else:   #relative path
            self.doc_root = os.path.abspath('.') + doc_path


    def start(self):
        """
        Server starts. For every client, server always creates a new thread to handle corresponding request.
        :return: None
        """
        self.listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listen_socket.bind((self.server_address, self.port))
        self.listen_socket.listen()

        while True:
            try:
                client_connection, client_address = self.listen_socket.accept()
            except IOError as e:
                code, msg = e.args
                # restart 'accept' if it was interrupted
                if code == errno.EINTR:
                    continue
                else:
                    raise

            #create new threads
            pid = os.fork()
            if pid == 0:  # child
                self.listen_socket.close()  # close child copy
                self.handle_request(client_address, client_connection)
                client_connection.close()
                os._exit(0)
            else:  # parent
                client_connection.close()  # close parent copy and loop over

    def handle_request(self, client_address, client_connection):
        """
        Created thread handles client's requests.
        :param client_address: client's address
        :param client_connection: the socket used to communicate with corresponding client
        :return: None
        """
        # receive client's request
        while (True):
            buffer = ""
            try:
                #normal running
                while(True):
                    client_connection.settimeout(5)
                    data = client_connection.recv(1024)
                    buffer += data.decode("UTF-8")
                    if buffer.find("\r\n\r\n") != -1:
                        break

                initial_line = buffer.split('\r\n\r\n', 1)[0].split('\r\n')[0:1][0]
                header_content = buffer.split('\r\n\r\n', 1)[0].split('\r\n')[1:]
                body = buffer.split('\r\n\r\n', 1)[1]

                print("initial_line:\n" + initial_line, end='\n')
                print("header_content:\n" + str(header_content), end='\n')
                print("body:\n" + body, end='\n')

                # Checking the request format
                checking_format_result, errorInfo = self.checkingFormat(initial_line, header_content, body)
                if checking_format_result != 0:
                    print("checking_format_result error " + str(checking_format_result) + "errorInfo: " + errorInfo,
                          end="\n")
                    self.sendResponse(client_connection, checking_format_result, "")
                    client_connection.close()
                    return

                # Checking target file
                checking_fileExistence_result, filePath = self.checkingFileExistence(initial_line)
                if checking_fileExistence_result == 404:
                    print("checking_fileExistence_result error " + str(404), end="\n")
                    self.sendResponse(client_connection, checking_fileExistence_result, "")

                # Send specified file
                self.sendResponse(client_connection, 200, filePath)

            except socket.timeout:
                # When the client doesn't send request within 5 seconds, client will give a response in terms of timeout mechanism
                if buffer != "":  #incomplete request
                    self.sendResponse(client_connection, 400, "")
                client_connection.close()
                break  # in exception branch, we still need to run break statement to jump out of while loop


    def checkingFormat(self, initial_line, header_content, body):
        """
        Check whether the format is correct
        :param initial_line: the first line in HTTP request
        :param header_content: headers in HTTP request
        :param body: body in HTTP request
        :return: 404 escaping the doc root, 400 bad request, 0 no error found
        """
        print("received initial line: "+ initial_line + "\n\n")


        # "abc/a" illegal
        if initial_line.split()[1][0] != '/':
            return 400, "illegal input"
        
        if len(initial_line.split()) != 3:
            return 400, "malformed"

        # Check initial_line(escaping the dir root)
        dirs = initial_line.split()[1].split('/')[1:]
        layer = 0
        for dir in dirs:
            if dir != '..':
                layer += 1
            else:
                layer -= 1
        if(layer < 0):
            #escaping the doc root
            return 404, "escaping the doc root"

        # Check header content
        correct_header_list = ["Cache-Control", "User-Agent", "Content-Type", "Accept", "Accept-Language", "Accept-Encoding", "Host", "Connection", "Cookie", "Date", "Pragma", "If-Modified-Since", "Range", "Upgrade-Insecure-Requests"]
        headers = dict()

        for header in header_content:
            colon_position = header.find(":")
            #no colon in header line
            if colon_position == -1:
                return 400, "no colon"
            #no space between colon and header value
            if header[colon_position+1] != ' ':
                return 400, "no space between colon and header value"
            #Malformed
            key, value = header.split(": ")
            if key not in correct_header_list:
                return 400, "malformed"

            headers[key] = value
        # Required header in missing
        if "Host" not in headers:
            return 400, "no Host header"

        # If above checking has been passed, return 0
        # Of course, we have not checked file existence yet
        return 0, "no error"

    def checkingFileExistence(self, initial_line):
        """
        Check whether the specified file exists
        :param initial_line: initial line in HTTP request
        :return: 404 no file. 200 file exists
        """
        dir_path = ""
        if initial_line.split()[1] == "/":
            dir_path = "/index.html"
        else:
            if initial_line.split()[1].find("..") == -1:
                dir_path += initial_line.split()[1]
            else:
                # There are legal ".."s in initial line like "/a/b/c/../d/e"
                stack = []
                dirs = initial_line.split()[1].split('/')[1:]
                for dir in dirs:
                    if dir != "..":
                        stack.append("/" + dir)
                    else:
                        stack.pop()

                for dir in stack:
                    dir_path += dir

        absPath = self.doc_root + dir_path
        if(os.path.exists(absPath) and not os.path.isdir(absPath)):
            return 200, absPath
        else:
            return 404, "File not found"


    def sendResponse(self, client_connection, status_code, filePath):
        """
        Send a response according to status code.
        :param client_connection: the socket used to communicate with corresponding client
        :param status_code: status code
        :param filePath: specified file path. For non-200 status code, the file path is ""
        :return:
        """
        response_initial_line = "HTTP/1.1 "
        response_headers = ""
        response = ""
        if(status_code != 200):
            if status_code == 400:
                response_initial_line += "400 Client Error\r\n"
            elif status_code == 404:
                response_initial_line += "404 Not Found\r\n"
            error_page = "<html><head><meta http-equiv='Content-Type' content='text/html; charset=utf-8' /><title>Error</title></head><body><B>" + str(status_code) + " Request error</B></body></html>"
            response_headers += "Server: Myserver 1.0\r\n"
            response_headers += "Content-Type: text/html\r\n"
            response_headers += "Content-Length: " + str(len(error_page)) + "\r\n\r\n"
            response += response_initial_line + response_headers + error_page

            client_connection.send(response.encode("UTF-8"))
        else: # status code is 200
            print("filepath: " + filePath, end="\n")
            response_initial_line += "200 OK\r\n"
            response_headers += "Server: Myserver 1.0\r\n"
            response_headers += "Last-Modified: " + str(os.path.getmtime(filePath)) + "\r\n"

            file_suffix = os.path.splitext(filePath)[1]
            if file_suffix == ".jpg" or file_suffix == ".jpeg":
                response_headers += "Content-Type: image/jpeg\r\n"
            elif file_suffix == '.png':
                response_headers += "Content-Type: image/png\r\n"
            elif file_suffix == ".html" or file_suffix == ".htm":
                response_headers += "Content-Type: text/html\r\n"

            response_headers += "Content-Length: " + str(os.path.getsize(filePath)) + "\r\n\r\n"

            if file_suffix == ".html" or file_suffix == ".htm":
                fp = open(filePath, "r")
                client_connection.send((response_initial_line + response_headers + fp.read()).encode("UTF-8"))
            else:
                fp = open(filePath, "rb")  #data input stream
                client_connection.send((response_initial_line + response_headers).encode("UTF-8") + fp.read())


if __name__ == "__main__":
    input_port = int(sys.argv[1])  # all arguments are string type
    input_doc_root = sys.argv[2]
    server = MyServer(input_port, input_doc_root)
    server.start()
