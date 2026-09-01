# coding=utf-8
import threading
from threading import RLock
from pymysql.sef_def_logger import MyLog
from . import nonregisteringdriver
from .blacklistmanager import BlackListManager
import time
import socket
import re
import copy
from . import connections
from . import err

class ConnectionManager:
    single_lock = RLock()
    prelist_lock = threading.Lock()
    grouplist_lock = threading.Lock()
    ipconnections_lock = threading.Lock()
    _instance = None
    def __new__(cls, *args, **kw):
        with cls.single_lock:
            if cls._instance is None:
                ConnectionManager._instance = object.__new__(cls)
        return ConnectionManager._instance
  
    def __init__(self,url: str,user: str,password:str):
        self._props = nonregisteringdriver.parse_url(url,None)#字典
        self.check_props()
        self._props['user'] = user
        self._props['password'] = password
        self._full_url = url
        self._all_iplist = self._init_all_iplist()#列表
        if self._props.get("masterConnection","false") == "true":
            self._all_group_host = self._init_all_group_host() #[proxygroup0,proxygroup1,...]初始化后只读,域名会被替换为IP
            self.check_same_group_info()#组间IP是否独立
            self._masterip = self.get_masterdn()#str
            self._group_iplist = self.update_group_iplist() #[[本地主],[本地备],[同城],[异地]]#masterip变化后，元素会重新维护
            self._pre_iplist = self._group_iplist#预处理列表   构成：[[本地主],[本地备],[同城],[异地]]
            #self._ip_connections = {} #{'ip':[connections]}masterip切换后使用该列表kill链接
        else:
            self._pre_iplist = self._all_iplist#预处理列表   构成：[本地主,本地备,同城,异地]
        self.check_allhost()

    @classmethod
    def get_instance(cls):
        return cls._instance
  
    def _init_all_group_host(self):
        groupnum = int(self._props.get("proxygroups","1"))
        result = []
        for i in range(groupnum):
            temp = []
            groupname = "proxygroup"+str(i)
            tmp = self._props.get(groupname)
            if tmp is None:
                errmessage = 'Failed to obtain {}, please check {} exists in the url.'.format(groupname,groupname)
                raise ValueError(errmessage)
            iplist = re.split(',|;',tmp)
            for _ in iplist:
                try:
                    host,port = _.split(':')
                except Exception:
                    errmessage = '{} format error, format is ip:port or domain:port.'.format(_)
                    raise ValueError(errmessage)
                try:
                    tmp_res = socket.getaddrinfo(host,None)
                except Exception as e:
                    raise e
                else:
                    for __ in tmp_res[:1]:
                        temp.append(str(__[4][0])+':'+port)
            result.append(temp)
        return result

    def add_ip_connections(self, conn: connections.Connection):
        ip = conn.host
        with ConnectionManager.ipconnections_lock:
            list = self._ip_connections.get(ip,[])
            list.append(conn)
            self._ip_connections[ip] = list

    def remove_ip_connections(self,conn: connections.Connection):
        ip = conn.host
        with ConnectionManager.ipconnections_lock:
            list = self._ip_connections.get(ip)
            list.remove(conn)
            if list:
                self._ip_connections[ip] = list
            else:
                del self._ip_connections[ip]

    def kill_nomasterip_connections(self): 
        with ConnectionManager.ipconnections_lock:
            for _ in self._ip_connections.keys():
                if _ == self._masterip:
                    continue
                else:
                    kill_conns = self._ip_connections[_]
                    for kill_conn in kill_conns:
                        try:
                            conn = connections.Connection(host=_,port=kill_conn.port,user=ConnectionManager.get_instance().get_props().get('user'),password=ConnectionManager.get_instance().get_props().get('paassword'))
                        except err.OperationalError:
                            pass
                        else:
                            if kill_conn.open:
                                cursor = conn.cursor()
                                cursor.execute('kill %s',kill_conn.thread_id())
                                kill_conn.close()
                            conn.close()
            self._ip_connections = {key: value for key, value in self._ip_connections.items() if key in [self._masterip]}    
    def set_props(self, p: dict):
        if self._props is None and p is not None:
            self._props = p

    def add_key_value_props(self,key,value):
        self._props[key] = value

    def get_props(self):
        return self._props
    
    def set_full_url(self, url: str):
        if url:
            self._full_url = url
    
    def get_full_url(self):
        return self._full_url
    
    def set_masterip(self, masterip: str):
        if self._masterip and not self._masterip.isspace():
            self._masterip = masterip
    
    def get_masterip(self):
        return self._masterip

    def set_pre_iplist(self, iplist: list):
        with ConnectionManager.prelist_lock:
            self._pre_iplist = iplist
        
    def get_pre_iplist(self):
        with ConnectionManager.prelist_lock:
            return copy.deepcopy(self._pre_iplist)

    def _init_all_iplist(self):
        groupnum = int(self._props.get("proxygroups","1"))
        result = []
        for i in range(groupnum):
            groupname = "proxygroup"+str(i)
            host = self._props.get(groupname)
            if host is None:
                errmessage = 'Failed to obtain {}, please check the url.'.format(groupname)
                raise ValueError(errmessage) 
            iplist = re.split(',|;',host)
            result.extend(iplist)
        return result
    
    def get_all_iplist(self):
        return copy.deepcopy(self._all_iplist)

    def set_group_iplist(self, group_iplist: list):
        with ConnectionManager.grouplist_lock:
            self._group_iplist = group_iplist

    def get_group_iplist(self):
        with ConnectionManager.grouplist_lock:
            return copy.deepcopy(self._group_iplist)
            
    #masterip不存在于所有组时，使用默认优先级:proxygroup0>proxygroup1>...
    def get_master_group_index(self):
        num_groups = int(self._props.get("proxygroups","1"))
        for i in range(num_groups):
            hosts = self._all_group_host[i]
            if hosts:
                for tmpip in hosts:
                    if ConnectionManager.get_instance().get_masterip() == nonregisteringdriver.parse_ipport(tmpip):
                        return i
        return 0

    #[[masterip], [masterip组内其他IP] [其他组的IP]]
    def update_group_iplist(self):
        group_host_list = []
        all_host_group = self._all_group_host
        if self._props is None:
            return group_host_list
        num_groups = len(all_host_group)
        if num_groups > 0:
                index = self.get_master_group_index()
                master_host_stuff = all_host_group[index]
                super_mater_hosts = []
                mater_hosts = []
                for tmp_ip in master_host_stuff:
                    if tmp_ip.startswith(self._masterip):
                        super_mater_hosts.append(tmp_ip)
                    else:
                        mater_hosts.append(tmp_ip)
                group_host_list.append(super_mater_hosts)
                group_host_list.append(mater_hosts)
                for i in range(num_groups):
                    if i == index:
                        continue
                    host_stuff = all_host_group[i]
                    if host_stuff:
                        group_host_list.append(host_stuff)
        return group_host_list

    def get_masterdn(self):
        masterip = None
        hosts = self._all_iplist
        for host in hosts:
            config = nonregisteringdriver.getconfig(host,ConnectionManager.get_instance().get_props()['user'],ConnectionManager.get_instance().get_props()['password'],ConnectionManager.get_instance().get_props())
            try:
                new_conn = connections.Connection(**config)
            except err.OperationalError:
                continue
            else:
                stmt = new_conn.cursor()
                stmt.execute("show variables like 'bind_address';")
                result = stmt.fetchone()
                if result:
                    masterip = result[1]
                stmt.close()
                new_conn.close()
                if masterip:
                    if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                        MyLog.get_instance().logger.info('Materip is set as database bind address:{}.'.format(masterip))
                    return masterip.decode('utf-8')
                else:
                    raise ValueError('Failed to get database bind address.')
        raise ValueError('No available ip:port.')
    
    #检查config是否满足要求
    def check_props(self):
        if self._props.get('loadbalance','') != '' and self._props.get('masterConnection','false') =='true':
            raise ValueError('Cannot set loadbalance and masterConnection at the same time.')

    #返回其他组ip列表
    def get_group_host(self,group_index: int):
        host_list = []
        try:
            num_groups = int(self._props.get("proxygroups", "1"))
            for i in range(num_groups):
                if i == group_index:
                    continue
                hosts = self._all_group_host[i]
                if hosts:
                        host_list.extend(hosts)
        except Exception as ex:
            raise ex
        return host_list

    #检查是否所有IP可用
    def check_allhost(self):
        for _ in self._all_iplist:
            config = nonregisteringdriver.getconfig(_,self._props.get('user'),self._props.get('password'),self._props)
            try:
                conn = connections.Connection(**config)
            except Exception:
                raise
            else:
                conn.close()

    #检查组内IP是否唯一
    @staticmethod
    def check_group_info(group_iplist: list):
        host = []
        for _ in group_iplist:
            try:
                ip,port = _.split(":")
            except Exception:
                raise
            host.append(ip)
        return len(set(host)) == len(host)

    #检查不同组IP是否独立
    def check_same_group_info(self):
        if self._props is None:
            return
        num_groups = int(self._props.get("proxygroups", "1"))
        for i in range(num_groups):
            cur_hosts = self._all_group_host[i]
            if not ConnectionManager.check_group_info(cur_hosts):
                raise ValueError("proxygroup" + str(i) + ":" + " has duplicate IP addresses.")
            other_hosts = self.get_group_host(i)
            for cur_ip in cur_hosts:
                try:
                    ip,port = cur_ip.split(':')
                except Exception:
                    raise
                for tmp_ip in other_hosts:
                    if tmp_ip.lower().startswith(ip.lower()):
                        raise ValueError("proxygroup" + str(i) + ":" + ip + " has same ip in other proxygroup.")

    def ip_connection_filter(self):
        if ConnectionManager.get_instance().get_props().get("masterConnection","false") == "true":
            newmasterip = ConnectionManager.get_instance().get_masterdn()
            oldmasterip = ConnectionManager.get_instance().get_masterip()
            if newmasterip != oldmasterip:#说明数据库绑定的IP已变
                ConnectionManager.get_instance().set_masterip(newmasterip)#设置masterip
                if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    MyLog.get_instance().logger.info('masterip changed from ip:{} to ip:{}.'.format(oldmasterip,newmasterip))
                ConnectionManager.get_instance().set_group_iplist(ConnectionManager.get_instance().update_group_iplist())#更新groupiplist
                ConnectionManager.get_instance().set_pre_iplist(ConnectionManager.get_instance().update_group_iplist())
            # black_iplist = copy.deepcopy(BlackListManager.get_instance().get_black_map())
            # if len(black_iplist)!=0:
            #     result = []
            #     monitor_list = copy.deepcopy(ConnectionManager.get_instance().get_group_iplist())
            #     for i in range(len(monitor_list)):
            #         if monitor_list[i]:
            #             monitor_list[i] = [x for x in monitor_list[i] if x not in black_iplist]
            #             result.append(monitor_list[i])
            #     ConnectionManager.get_instance().set_pre_iplist(result)
        else:
            ConnectionManager.get_instance().set_pre_iplist(ConnectionManager.get_instance().get_all_iplist())
            black_iplist = BlackListManager.get_instance().get_black_map()
            if len(black_iplist)!=0:
                result = []
                monitor_list = ConnectionManager.get_instance().get_all_iplist()
                for host in monitor_list:
                    if host not in black_iplist:
                        result.append(host)
                ConnectionManager.get_instance().set_pre_iplist(result)
        
def connection_filter_thread():
    interval_time = 3
    props = ConnectionManager.get_instance().get_props()
    interval_time = int(props.get("intervalTime", "3"))
    interval_time = interval_time if interval_time > 0 else 3
    if ConnectionManager.get_instance().get_props().get("masterConnection","false") == "true":
        while True:
            newmasterip = ConnectionManager.get_instance().get_masterdn()
            oldmasterip = ConnectionManager.get_instance().get_masterip()
            if newmasterip != oldmasterip:#说明数据库绑定的IP已变
                ConnectionManager.get_instance().set_masterip(newmasterip)#设置masterip
                if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    MyLog.get_instance().logger.info('masterip changed from ip:{} to ip:{}.'.format(oldmasterip,newmasterip))
                ConnectionManager.get_instance().set_group_iplist(ConnectionManager.get_instance().update_group_iplist())#更新groupiplist
                ConnectionManager.get_instance().set_pre_iplist(ConnectionManager.get_instance().update_group_iplist())
                #ConnectionManager.get_instance().kill_nomasterip_connections()#kill 非masterip connection
            black_iplist = copy.deepcopy(BlackListManager.get_instance().get_black_map())
            if len(black_iplist)==0:
                time.sleep(interval_time)
                continue
            else:
                result = []
                monitor_list = copy.deepcopy(ConnectionManager.get_instance().get_group_iplist())
                for i in range(len(monitor_list)):
                    if monitor_list[i]:
                        monitor_list[i] = [x for x in monitor_list[i] if x not in black_iplist]
                        result.append(monitor_list[i])
                ConnectionManager.get_instance().set_pre_iplist(result)
                #if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    #MyLog.get_instance().logger.info('Current preiplist is {}.'.format(result))
                time.sleep(interval_time)
    else:
        while True:
            ConnectionManager.get_instance().set_pre_iplist(ConnectionManager.get_instance().get_all_iplist())
            black_iplist = BlackListManager.get_instance().get_black_map()
            if len(black_iplist)==0:
                time.sleep(interval_time)
                continue
            else:
                result = []
                monitor_list = ConnectionManager.get_instance().get_all_iplist()
                for host in monitor_list:
                    if host not in black_iplist:
                        result.append(host)
                ConnectionManager.get_instance().set_pre_iplist(result)
                #if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    #MyLog.get_instance().logger.info('Current preiplist is {}.'.format(result))
                time.sleep(interval_time)