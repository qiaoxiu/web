rabbitmq 是消息队列，比较常见的实现方案；
消息队列可以实现以下功能

1.异步
2.分发流量
3.系统解耦
4.延时消费

在互联网公司消息中间件 应用广泛 openstack 使用rabbitmq 分发任务

其基本原理就是 消费者 和生产者 通过 中间代理人 转发消息 完成 消费者 消费消息


　当producer(consumer)要生产(消费)消息时，需要与服务器建立一个长连接，
 在RabbitMQ中称为Connection，为解决客户端与服务端所产生频繁连接的问题，由于会大量的消耗服务器内存，
 这里引入消息通道的概念，在保持长连接的情况下，可以通过建立Channel的方式与服务器通讯，当有请求时就会建立通道，
 结束则关闭通道。在RabbitMQ中，一般的做法不会让消息直接发送到消息队列中，这里引入了Exchange(交换机)的概念，
 通过交换机来实现消息更加灵活的分发，交换机没有实际的进程，而队列是有的，它只是一个地址列表，在队列创建的时候会与Exchange绑定一个专属的key，
 在生产者生产消息的时候也会指定这个key，那么Exchange就会通过这个key去匹配Queue，从而实现灵活分发。然后消费方会通过订阅指定的队列去消费消息。
 在RabbitMQ中有Virtual Host虚拟机的概念，它可以当成是一个小型的MQ，一个RabbitMQ服务器上可以有多个虚拟机，相互之间是隔离的，当然不同的虚拟机之间可以有相同的交换机与队列，
 可以实现资源的隔离。
 
 
 分发有多重模式 其中 主要使用三种进行  
 
 1.订阅 
   ①交换机定义类型为：fanout

  ②交换机绑定多个队列

  ③生产者将消息发送给交换机，交换机复制同步消息到后端所有的队列中

  一些场景：邮件群发
 2. 路由
 
    ①交换机定义类型为：direct

    ②交换机绑定多个队列，队列绑定交换机时，给交换机提供了一个routingkey（路由key）

    ③发布订阅时，所有fanout类型的交换机绑定后端队列用的路由key都是“”；在路由模式中需要绑定队列时提供当前队列的具体路由key

    一些场景：错误消息的接收和提示
    
  3.topic
  
      ①交换机定义类型为：topic

      ②交换机绑定多个队列，与路由模式非常相似，做到按类划分消息

       ③路由key队列绑定的通配符如下：#表示任意字符串，*表示没有特殊符号（单词）的字符串


rabbimq 使用起来简单，但是设计到消息 可靠性 消息丢失 顺序消费 内存性能优化等 需要大量实践


rabbitmq 安装  环境是centos 


   yum -y install erlang socat
   wget https://www.rabbitmq.com/releases/rabbitmq-server/v3.6.10/rabbitmq-server-3.6.10-1.el7.noarch.rpm
   rpm –import https://www.rabbitmq.com/rabbitmq-release-signing-key.asc
   rpm -Uvh rabbitmq-server-3.6.10-1.el7.noarch.rpm
   systemctl start rabbitmq-server
   systemctl status rabbitmq-server
   rabbitmq-plugins enable rabbitmq_management
   chown -R rabbitmq:rabbitmq /var/lib/rabbitmq/
   rabbitmqctl add_user admin 123456
   rabbitmqctl set_user_tags admin administrator
   rabbitmqctl set_permissions -p / admin “.*” “.*” “.*”
