tornado 框框 是 python三大框架之一，区别于Flask Django 是一个自带网络服务器的异步非阻塞框架，面向协程编程，性能更高 单进程可以 支持上万请求，不会占用过多服务器资源
不过由于本身只是提供框架主体部门，db 权限 等相关工作 需要自己封装，在python2.x版本是自己实现的eventloop 在最新版本是使用python3.4以后的asyncio库实现eventloop 
配合selectors 库提供 套接字的异步读写回调，底层是调用内核的epoll 或 select 


tornado 涉及到的几个概念
1.httpServer 完整的http服务器  继承tcpServer 处理http 相关的 请求和相应 
2.tcpServer  完整的tcp服务器实现，处理 套接字的相关
3.IOStream 进行从套接字进行 数据读写类
4.HTTP1ServerConnection http连接服务器 
5.HTTP1Connection http协议中 处理客户端请求的连接
6.application 应用 用户进行路由映射
7.request hhtp请求的request对象
8.requestHanlder 用户编写的业务实现类






tornado 完整的请求过程 

1.创建application 并监听端口号；application 监听 调用httpServer  并调用 TCPServer 进行 端口号监听，进行套接字创建，并将套接字进行  通过ioloop 注册 读事件 回调  ，其底层是调用的asyncio
来实现注册事件，当读事件触发时候 进行回调函数的调用 这里的回调函数是self._handle_connection，也就是在接受到客户端请求连接的时候 根据客户端连接 创建IOStream，然后进行 header body 的读写

2.HTTP1Connection的_read_message来进行套接字上的数据进行读取，首先从套接字读取到 缓存，然后在计算header 位置 读取header 头部信息，解析头部信息，然后根据长连接 头部信息 等 创建http的request对象

3.根据产生的request 对象来定位handler对象； _RoutingDelegate find_handler 调用 Application 的 find_handler 来定位handler ，就是通过request 来定位target 和rule 最终得到_HandlerDelegate
  对象
  
4.如果存在body数据，从套接字中将数据写入缓存，根据Content-Length 大小读取完整body 数据  最终运行 _HandlerDelegate 的 finish 方法 来解析body  运行 hanlder业务的execute函数

5.execute函数内部就是构造hanlder业务类，并调用业务类的execute 函数 开始接触业务逻辑代码准备工作，首先调用 prepare函数 进行逻辑处理前的准备工作 然后调用 GET POST业务逻辑代码，业务逻辑
   根据情况回写数据 write 或者 render ，进行注册数据 并最终调用flush finish 函数 组织好header body 数据 写入 iostream对象 最终根据套接字写入客户端
   
   
   关于 asyncio  可以看这个博客，有比较详细的介绍 
    https://www.zhihu.com/people/zhihu_lh/posts
    
    asyncio在python3.4提供的，区别于 生成器和 协程的区别，提出了futrue task 概念 
    futrue  等待时间循环调度的任务对象  调用futrue.set_rsult() 进行赋值  调用 futrue.result() 获取协程的结果 是一个可等待对象 其实就是等待调用回调函数的载体
    task  是futrue 的子类，一般开发时候 将函数 创建成task 可等待对象 进行 等待调度 执行相应的回调函数
    
    
    整个 asyncio 创建了 几个对象  reader  writer schel _ready  分别为可读 对象 可写对象 注册在selectors中 当发生 可读可写事件的时候 epoll 会返回相应的 文件文件描述符
    和相应回调函数一起 进行加入 schel当中，进行统一调度 基于及时进行按照顺序进行相应调度 __ready 可调度任务列表，当符合调度的要求 进行调用回调函数完成该任务 
    
    hanlder 概念 ， 将回调函数进行封装 然后交给schel进行调度，当可读可写事件发生， 或者 用户调用 asyncio 的相应方法 比如 call_soon call_later call_at add_callback 等函数 将回调     进行添加到schel 当中 进行调度， 事件循环 回调用once函数，进行timeout计算 根据 超时设置 将符合调度的任务加入到_ready 中 ，最后 循环遍历_ready 列表 安时间顺序调用 每个hanlder对     象的 _run 方法 调用相应的 回调函数 
    
    以上就是asyncio  提供的事件循环调用来实现的协程的处理方式，另外其实现了很多功能 包括 网络 流 多进程 多线程等实现 可参考官网中文文档 
    https://docs.python.org/zh-cn/3/library/asyncio-eventloop.html#
    
