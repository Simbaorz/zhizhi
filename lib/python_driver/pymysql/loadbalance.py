# -*- coding: utf-8 -*-
import random
import copy
import threading
import time
from . import connections,err
from .sef_def_logger import MyLog
from .blacklistmanager import run as black_moniter_thread,BlackListManager
from .connectionmanager import ConnectionManager
from . import nonregisteringdriver


loadbalance_logg = MyLog().logger

def init(url: str,user: str,password: str,log_config: dict = None):
    global conectionmanager, blacklistcon, loadbalance_logg
    loadbalance_logg = MyLog(log_config)
    conectionmanager = ConnectionManager(url,user,password)
    blacklistcon = BlackListManager(ConnectionManager.get_instance().get_props())
    #filter_thread = threading.Thread(target=connection_filter_thread)
    #filter_thread.daemon=True
    #filter_thread.start()
    moniter_thread = threading.Thread(target=black_moniter_thread)
    moniter_thread.daemon=True
    moniter_thread.start()
    

def get_instance(user: str = None, password: str = None):
    ConnectionManager.get_instance().ip_connection_filter()
    if user is None:
        user = ConnectionManager.get_instance().get_props().get('user')
    if password is None:
        password = ConnectionManager.get_instance().get_props().get('password')
    ip_port_list = ConnectionManager.get_instance().get_pre_iplist()
    if ConnectionManager.get_instance().get_props().get("masterConnection","false") == "true":
        for _ in range(len(ip_port_list)):
            while ip_port_list[_]:
                host=random.sample(ip_port_list[_],1)[0]
                ip_port_list[_].remove(host)
                config = nonregisteringdriver.getconfig(host,user,password,ConnectionManager.get_instance().get_props())
                try:
                    conn = connections.Connection(**config)
                except err.OperationalError as e:
                    if e.args[0] == 2003:
                        if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                            MyLog.get_instance().logger.info('Failed to link host:{}, host:{} will append into minitor list.'.format(host,host))
                            MyLog.get_instance().logger.info(e)
                        ip,port = host.split(':')
                        config={'user':user,'password':password,'host':ip,'port':int(port)}
                        BlackListManager.get_instance().add_monitor_host(host,config)
                        if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                            MyLog.get_instance().logger.info('Current monitor list is {}.'.format(BlackListManager.get_instance().get_monitor_map().keys()))
                    else:
                        raise
                else:
                    #ConnectionManager.get_instance().add_ip_connections(conn)
                    return conn
        raise ValueError('No available ip:port.')             
    else:
        while ip_port_list:
            host=random.sample(ip_port_list,1)[0]
            ip_port_list.remove(host)
            config = nonregisteringdriver.getconfig(host,user,password,ConnectionManager.get_instance().get_props())
            try:
                conn = connections.Connection(**config)
            except err.OperationalError as e:
                if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    MyLog.get_instance().logger.info('Failed to link host:{},host:{} append into minitor list.'.format(host,host))
                    MyLog.get_instance().logger.info(e)
                ip,port = host.split(':')
                config={'user':user,'password':password,'host':ip,'port':int(port)}
                BlackListManager.get_instance().add_monitor_host(host,config)
                if ConnectionManager.get_instance().get_props().get('printlog','false') == 'true':
                    MyLog.get_instance().logger.info('Current monitor list is {}.'.format(BlackListManager.get_instance().get_monitor_map().keys()))
            else:
                return conn
        raise ValueError('No available ip:port.')

def close_instance(conn: connections.Connection):
    try:
        if conn.open:
            #if ConnectionManager.get_instance().get_props().get('masterConnection','false') == 'true':
                #ConnectionManager.get_instance().remove_ip_connections(conn)
            conn.close()
    except Exception:
        raise

def check_changed():
    newmasterip = ConnectionManager.get_instance().get_masterdn()
    oldmasterip = ConnectionManager.get_instance().get_masterip()
    return newmasterip != oldmasterip, newmasterip, oldmasterip

# 将loadbalance字段里ip和port解析出来，将不在黑名单中的ip,port放入列表ip_port_list中
def deloadbalance(loadbalance,ip_port_blacklist):
    
    ip_port_list = [] 
    
    # 将loadbalance按","分割，产生预处理列表ip_port_pre_list
    ip_port_pre_list = loadbalance.split(",")
    
    for i in range(len(ip_port_pre_list)):
        # 将预处理列表ip_port_pre_list按":"分割
        result = ip_port_pre_list[i].split(":")
        result[1] = int(result[1])
        
        # 将不在黑名单中的ip,port放入列表ip_port_list中
        if ip_port_blacklist.count(result) == 0:
            ip_port_list.append(result)
            
    return ip_port_list


# 随机取ip_port_list中一组不在黑名单的ip,port连接，连接成功则返回连接和黑名单，
# 失败则加入黑名单再随机取下一组ip,port连接，全部连接失败则返回None和黑名单
def randomcon(loadbalance,user,passwd,charset,database=None):
    
    ip_port_blacklist = []
    ip_port_list = deloadbalance(loadbalance,ip_port_blacklist)
    num = len(ip_port_list)
    ran = random.sample(range(0,num), num)
    
    # 判断ip_port_list里有无元素，如果没有则直接返回
    if len(ip_port_list) == 0:
        return None, ip_port_blacklist
    
    i = 0
    while i<num:
        rannum = ran[i]
        
        # 如果ip,port在黑名单中则取下一组，ip_port_list全取完都连接不成功则全部连接失败
        if ip_port_blacklist.count(ip_port_list[rannum]) != 0:
            loadbalance_logg.info("ip,port:{}在黑名单中,取下一组ip,port连接".format(ip_port_list[rannum]))
            i += 1
            if i == num:
                loadbalance_logg.info("全部连接失败")
                return None, ip_port_blacklist
            continue
        
        try:
            loadbalance_logg.info("尝试连接的ip,port:"+str(ip_port_list[rannum]))
            conn = connections.Connection(host = ip_port_list[rannum][0], port = ip_port_list[rannum][1], user = user, passwd = passwd, charset = charset,database = database)
            
        except Exception :
            ip_port_blacklist.append(ip_port_list[rannum])
            loadbalance_logg.info("ip,port:{}连接失败加入黑名单"+str(ip_port_list[rannum]))
            i += 1
            if i == num:
                loadbalance_logg.info("全部连接失败")
                return None, ip_port_blacklist
            continue
        
        loadbalance_logg.info("连接成功的ip,port"+str(ip_port_list[rannum]))
        break
    
    return conn, ip_port_blacklist


# 取黑名单里所有的ip,port连接，连接成功则将其从黑名单中去除，
# 连接失败则等待threadtime后再次连接，最后返回最后的黑名单    
def blacklistcon(ip_port_blacklist,user,passwd,charset):
    
    def blistcon(ip_port_blacklist,user,passwd,charset,threadtime):
        
        # starttime = time.strftime("%Y%m%d%H%M%S")
        # now = time.strftime("%Y%m%d%H%M%S")
        
        # 判断黑名单里有无元素，如果没有则直接返回
        if len(ip_port_blacklist) == 0:
            return
        
        ip_port_consuccess = []
        
        for i in range(len(ip_port_blacklist)):
            while True:
                
                # if (int(starttime)+3*(i+1)*threadtime) <= int(now):
                #     break
                # now = time.strftime("%Y%m%d%H%M%S")
                
                try:
                    loadbalance_logg.info("尝试连接ip,port:"+str(ip_port_blacklist[i]))
                    conn = connections.Connection(host = ip_port_blacklist[i][0], port = ip_port_blacklist[i][1], user = user, passwd = passwd, charset = charset)
                    conn.close()
                
                except Exception :
                    loadbalance_logg.info("ip,port:{}连接失败，{}秒后重新连接".format(ip_port_blacklist[i], threadtime))
                    time.sleep(threadtime)
                    continue
                
                loadbalance_logg.info("ip,port:{}连接成功，从黑名单去除".format(ip_port_blacklist[i]))
                # 记录黑名单中连接成功的ip,port
                ip_port_consuccess.append(ip_port_blacklist[i])
                break
        
        # 根据记录删除黑名单中连接成功的ip,port
        for i in range(len(ip_port_consuccess)):
            lock = threading.Lock()
            lock.acquire()
            ip_port_blacklist.remove(ip_port_consuccess[i])
            lock.release()
        
    def run(threadtime):
        thread = threading.Thread(target = blistcon,args = (ip_port_blacklist,user,passwd,charset,threadtime))
        thread.start()
        thread.join()
    
    threadtime = 2 # 连接失败后重新连接等待的时间
    run(threadtime)
   
    return ip_port_blacklist
            














