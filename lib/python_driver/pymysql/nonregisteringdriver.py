# coding=utf-8
import copy
#url:"pymysql:goldendb://ip:port,ip1:port1/database?config"
def parse_ipport(ipport:str):
        host,port = ipport.split(":")
        return host

#url:"pymysql:goldendb://ip:port,ip1:port1/database?config0=parameter0&config1=parameter1"
def parse_url(url: str, defaults: dict):
    #仅支持如下形式开始的URL
    URL_PREFIX = "pymysql:goldendb://"
    url_props = copy.deepcopy(defaults) if defaults else {}
    if url is None:
        return None
    elif not url.startswith(URL_PREFIX):
        raise ValueError('The url must start with "pymysql:goldendb://".')
    else:
        beginning_of_slashes = url.find("//")
        index = url.find("?")
        if index != -1:
            host_stuff = url[index + 1:]
            url = url[:index]
            query_params = host_stuff.split('&')
            for parameter_value_pair in query_params:
                config_name, parameter = parameter_value_pair.split('=')
                url_props[config_name] = parameter
            
        url = url[beginning_of_slashes + 2:]
        slash_index = url.find("/")
        if slash_index != -1:
            host_stuff = url[:slash_index]
            url_props["database"] = url[slash_index + 1:]
        else:
            host_stuff = url
        url_props["proxygroup0"] = host_stuff
    return url_props

def getconfig(host: str,user: str, password: str,prop: dict):
    config = {}
    ipport = host.split(":")
    config["host"] = ipport[0]
    config["port"] = int(ipport[1])
    config["user"] = user
    config["password"] = password
    config["database"] = prop.get("database",None)
    config["charset"] = prop.get("charset",None)
    config["unix_socket"] = prop.get("unix_socket",None)
    config["sql_mode"] = prop.get("sql_mode",None)
    config["read_default_file"] = prop.get("read_default_file",None)
    config["conv"] = prop.get("conv",None)
    config["use_unicode"] = prop.get("use_unicode",None)
    config["client_flag"] = int(prop.get("client_flag",0))
    config["init_command"] = prop.get("init_command",None)
    config["connect_timeout"] = int(prop.get("connect_timeout","10"))
    config["autocommit"] = prop.get("autocommit",'false')=='true'
    return config
    