# coding=utf-8
import threading
from threading import RLock
import copy
import time
import concurrent.futures
from . import connections,err
from .sef_def_logger import MyLog

executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

class BlackListManager(object):
    single_lock = RLock()
    monitor_lock = threading.Lock()
    black_lock = threading.Lock()

    def __new__(cls, *args, **kw):
        with cls.single_lock:
            if not hasattr(BlackListManager, "_instance"):
                BlackListManager._instance = object.__new__(cls)
        return BlackListManager._instance
    
    def __init__(self,props: dict):
        self._monitor_host_map = {}#str:dict{'host':'','port':3306,'user':'','password':'','connect_timeout':10}
        self._black_host_map = {}#str:dict
        self._props = props#模块解耦，复制一份ConnectionManager的props成员，不在访问ConnectionManager模块
    
    @classmethod
    def get_instance(cls):
        return cls._instance
    
    def get_monitor_map(self) ->dict :
        with BlackListManager.monitor_lock:
            return copy.deepcopy(self._monitor_host_map)

    def get_black_map(self) ->dict :
        with BlackListManager.black_lock:
            return copy.deepcopy(self._black_host_map)

    def add_monitor_host(self,host: str,config: dict):
        if host not in self._monitor_host_map.keys():
            with BlackListManager.monitor_lock:
                self._monitor_host_map[host] = config
            if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
                MyLog.get_instance().logger.info('Host:{} append into monitor map.'.format(host))

    def remove_monitor_host(self, host: str):
        if host in self._monitor_host_map.keys():
            with BlackListManager.monitor_lock:
                del self._monitor_host_map[host]
            if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
                MyLog.get_instance().logger.info('Host:{} remove from monitor map.'.format(host))

    def add_black_host(self, host: str, config: dict):
        if host not in self._black_host_map:
            with BlackListManager.black_lock:
                self._black_host_map[host] = config
            if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
                MyLog.get_instance().logger.info('Host:{} append into black map.'.format(host))

    def remove_black_host(self, host: str):
        if host in self._black_host_map:
            with BlackListManager.black_lock:
                del self._black_host_map[host]
            if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
                MyLog.get_instance().logger.info('Host:{} remove from black map.'.format(host))

    def get_props(self):
        return self._props

def check_conn(config: dict, num_retries: int):
    for attempts in range(num_retries):
        try:
            new_conn = connections.Connection(**config)
        except err.OperationalError as e:
            if e.args[0]==2003:
                if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
                    MyLog.get_instance().logger.info('Failed to link host:{}-{} the {}-th time.'.format(config.get('host'),config.get('port'),attempts+1))
                    MyLog.get_instance().logger.info(e)
                continue
            else:
                raise
        else:
            return new_conn
    return None

def close_conn(conn):
    try:
        if conn.open:
            conn.close()
    except err.Error as e:
        if BlackListManager.get_instance().get_props().get('printlog','false') == 'true':
            MyLog.get_instance().logger.info(e)

def run():
    while True:
        monitor_list = BlackListManager.get_instance().get_monitor_map()
        props = BlackListManager.get_instance().get_props()
        interval_time = int(props.get("intervalTime", "3"))
        interval_time = interval_time if interval_time > 0 else 3
        if monitor_list:
            for host,config in monitor_list.items():
                conn = check_conn(config, 3)
                BlackListManager.get_instance().remove_monitor_host(host)
                if not conn:
                    BlackListManager.get_instance().add_black_host(host,config)
                    black_time = int(props.get("blackTaskTime", "60"))
                    black_time = black_time if black_time >0 else 60
                    executor.submit(black_list_task,host,config,black_time)
                else:
                    close_conn(conn)
        time.sleep(interval_time)

def black_list_task(host: str, config: dict,black_time: time):
    time.sleep(black_time)
    if config:
        conn = check_conn(config, 1)
        if conn:
            BlackListManager.get_instance().remove_black_host(host)
            close_conn(conn)
        else:
            executor.submit(black_list_task,host,config,black_time)