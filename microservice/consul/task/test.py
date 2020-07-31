import consul

class Consul(object):
    def __init__(self, host, port):
        '''初始化，连接consul服务器'''
        self._consul = consul.Consul(host, port)

    def RegisterService(self, name, host, port, tags=None):
        tags = tags or []
        # 注册服务
        self._consul.agent.service.register(
            name,
            name,
            host,
            port,
            tags,
            # 健康检查ip端口，检查时间：5,超时时间：30，注销时间：30s
            check=consul.Check().tcp(host, port, "5s", "30s", "30s"))

    def GetService(self, name):
        services = self._consul.agent.services()
        service = services.get(name)
        if not service:
            return None, None
        addr = "{0}:{1}".format(service['Address'], service['Port'])
        return service, addr

if __name__ == '__main__':
    host="10.60.0.221" #consul服务器的ip
    port="9500" #consul服务器对外的端口
    consul_client=Consul(host,port)

    name="seq"
    port=8866
    #consul_client.RegisterService(name,host,port)

    check = consul.Check().tcp(host, port, "5s", "30s", "30s")
    print(check)
    res=consul_client.GetService("seq")
    print(res)

