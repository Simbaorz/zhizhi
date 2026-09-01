[![Documentation Status](https://readthedocs.org/projects/pymysql/badge/?version=latest)](https://pymysql.readthedocs.io/)
[![image](https://coveralls.io/repos/PyMySQL/PyMySQL/badge.svg?branch=main&service=github)](https://coveralls.io/github/PyMySQL/PyMySQL?branch=main)

# PyMySQL

This package contains a pure-Python MySQL client library, based on [PEP
249](https://www.python.org/dev/peps/pep-0249/).

## Requirements

- Python -- one of the following:
  - [CPython](https://www.python.org/) : 3.7 and newer
  - [PyPy](https://pypy.org/) : Latest 3.x version
- MySQL Server -- one of the following:
  - [MySQL](https://www.mysql.com/) \>= 5.7
  - [MariaDB](https://mariadb.org/) \>= 10.3

## Installation

Package is uploaded on [PyPI](https://pypi.org/project/PyMySQL).

You can install it with pip:

    $ python3 -m pip install PyMySQL

To use "sha256_password" or "caching_sha2_password" for authenticate,
you need to install additional dependency:

    $ python3 -m pip install PyMySQL[rsa]

To use MariaDB's "ed25519" authentication method, you need to install
additional dependency:

    $ python3 -m pip install PyMySQL[ed25519]

## Documentation

Documentation is available online: <https://pymysql.readthedocs.io/>

For support, please refer to the
[StackOverflow](https://stackoverflow.com/questions/tagged/pymysql).

## Example

The following examples make use of a simple table

``` sql
CREATE TABLE `users` (
    `id` int(11) NOT NULL AUTO_INCREMENT,
    `email` varchar(255) COLLATE utf8_bin NOT NULL,
    `password` varchar(255) COLLATE utf8_bin NOT NULL,
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin
AUTO_INCREMENT=1 ;
```

``` python
import pymysql.cursors

# Connect to the database
connection = pymysql.connect(host='localhost',
                             user='user',
                             password='passwd',
                             database='db',
                             cursorclass=pymysql.cursors.DictCursor)

with connection:
    with connection.cursor() as cursor:
        # Create a new record
        sql = "INSERT INTO `users` (`email`, `password`) VALUES (%s, %s)"
        cursor.execute(sql, ('webmaster@python.org', 'very-secret'))

    # connection is not autocommit by default. So you must commit to save
    # your changes.
    connection.commit()

    with connection.cursor() as cursor:
        # Read a single record
        sql = "SELECT `id`, `password` FROM `users` WHERE `email`=%s"
        cursor.execute(sql, ('webmaster@python.org',))
        result = cursor.fetchone()
        print(result)
```

This example will print:

``` python
{'password': 'very-secret', 'id': 1}
```

## Resources

- DB-API 2.0: <https://www.python.org/dev/peps/pep-0249/>
- MySQL Reference Manuals: <https://dev.mysql.com/doc/>
- MySQL client/server protocol:
  <https://dev.mysql.com/doc/internals/en/client-server-protocol.html>
- "Connector" channel in MySQL Community Slack:
  <https://lefred.be/mysql-community-on-slack/>
- PyMySQL mailing list:
  <https://groups.google.com/forum/#!forum/pymysql-users>

## License

PyMySQL is released under the MIT License. See LICENSE for more
information.


'''
pymysql使用步骤
1)初始化驱动资源,不能二次调用,二次初始化行为未定义
pymysql.init(url='###',user='###',password='###',log_config=None)
2)获取连接
不传递user、password则使用初始化时的参数
conn = pymysql.getinstance(user='###',password='###')
cursor = conn.cursor()
业务流程
cursor.close()
conn.commit()
3)关闭连接
pymysql.closeinstance(conn)


NOTE:
本文档用于指导业务人员通过pymysql访问GoldenDB数据库，内含参数修改全景、各版本新特性、场景使用推荐三个大章节。
Total param change：
-----------------
| 变更类型  | 变更版本      |  参数名  | 参数说明 | 取值范围 | 上一版本默认值                  | 默认值     | 
| :----  |:----------| :----  |  :----  | :----  |:-------------------------|:--------|

| add | 1.0.3 | masterConnection  | masterConnection=true,开启主CN建链功能 | true/false | false                    |


版本特性：

Edition：【1.0.3】 , Archieve date:2023/12/10
1.主CN建链功能
后台线程查找主CN，根据结果维护各组优先级，主CN的IP不在url中，则使用默认的组优先级(proxygroup0,proxygroup1,...,proxygroupn)
此功能有如下限制：
    1)goldendb环境中主DN的IP即为主CN的IP
    2)相同的IP不能配置到不同的组
    3)相同的IP不能配置到同组
    4)IP或域名必须配置端口

|  参数名  | 参数说明 | 取值范围 | 默认值 | 
| :----  | :----  | :----  |  :----  | 
| masterConnection  | masterConnection=true,开启主CN建链功能 | true/false |false|
1)masterconnection功能支持url配域名，url中域名与IP是一对一的关系，
  不支持一个域名对应多个IP的配置
2)业务端与CN之间不能有F5之类的负载均衡


常用的pymysql url配置示例
=================
 pymysql URL基本格式：
-----------------
    pymysql:goldendb://DBProxyIP:ClusterPort/DBName?parameterName1=parameterValue1&parameterName2=parameterValue2 ...
    样例：pymysql:goldendb://192.168.100.7:7788/testdb?masterConnection=false

    主CN样例：pymysql:goldendb://192.168.100.7:7788,192.168.100.8:7788,192.168.100.9:7788/testdb?masterConnection=true&proxygroups=3&proxygroup1=192.168.100.10:7788,192.168.100.11:7788,192.168.100.12:7788&proxygroup2=192.168.100.13:7788,192.168.100.14:7788,192.168.100.15:7788
    注:192.168.100.7:7788,192.168.100.8:7788,192.168.100.9:7788为默认的proxygroup0
    若主CN为192.168.100.8,则各组优先级[192.168.100.8:7788]>[192.168.100.7:7788,192.168.100.9:7788]>[proxygroup1]>[proxygroup2]
    若主CN为192.168.100.10,则各组优先级[192.168.100.10:7788]>[192.168.100.11:7788,192.168.100.12:7788]>[proxygroup0]>[proxygroup2]
    若主CN为192.168.100.15,则各组优先级[192.168.100.15:7788]>[192.168.100.13:7788,192.168.100.14:7788]>[proxygroup0]>[proxygroup1]
    后台线程维护该优先级,获取连接时直接根据优先级建链,高优先级无可用链路，则访问下一优先级分组

'''

python.conect接口支持random负载均衡示例
```python
import pymysql
user = 'xxx'
passwd = 'xxx'
ip = 'xxx'
port = xxx
ip_port_lists = 'ip1:port1,ip2:port2,...'
conn = pymysql.connect(user=user,password=passwd,load_balance_mode="random",ip_port_lists=ip_port_lists)

conn1 = pymysql.connect(user=user,password=passwd,host=ip,port=port,load_balance_mode="random",ip_port_lists=ip_port_lists)

conn1与conn的区别是：ip_port_lists所有配置建链失败后，以ip:port在尝试一次建链，此配置优先级最低。

```