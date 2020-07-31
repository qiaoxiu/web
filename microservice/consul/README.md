服务发现是 微服务的重要部分，没有服务发现 微服务就不能灵活的针对应用的部署和发现问题，其使用受限，而服务发现就是为了使服务和调用者之间进行解耦，不在强依赖在一起
当服务启动的时候 将自己注册到服务当中，而不关心是为谁提供服务，而客户端或者消费者会去服务发现服务查找当前指定服务名，获取到指定服务名 获取到指定ip 端口号进行连接调用

服务发现实现方案有很多种，其中主流开源的是zookeeper consul，这里使用consul 来实现，关于consul 的介绍 后续会补充上

首先启动服务发现服务
然后服务提供者启动服务将服务ip port name 注册到服务发现服务当中 
调用者启动后需要调用逻辑就调用服务发现服务进行 指定服务名称的查询，获取到指定ip port完成服务调用 

安装单节点的consul 例子来讲解下服务发现逻辑，后续会在补充 分布式 高可用的服务发现搭建和使用 

首先安装consul 
 wget https://releases.hashicorp.com/consul/1.5.1/consul_1.5.1_linux_amd64.zip
 解压会生成consul文件
 
 consul agent --data-dir data  -server -ui -bootstrap -bind=127.0.0.1
 启动consul 服务 端口号是9500 可访问http://127.0.0.1:9500/ui 查看服务 
 
 task目录有一个服务注册的demo 执行 python test.py 需要提前安装consul  python 库 
 运行完在看页面可以发现服务已经注册了 其中还包括该服务的健康状态 
 然后调用 http://127.0.0.1:9500/v1/health/service/seq  可以获取seq这个服务的ip port 等信息 完成服务发现
