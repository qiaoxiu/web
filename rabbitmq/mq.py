import pika
import json

credentials = pika.PlainCredentials('admin', '123456')  # mq用户名和密码
# 虚拟队列需要指定参数 virtual_host，如果是默认的可以不填。
connection = pika.BlockingConnection(pika.ConnectionParameters(host = '10.60.0.221',port = 5672,virtual_host = '/test_mq',credentials = credentials))
channel=connection.channel()
# 声明exchange，由exchange指定消息在哪个队列传递，如不存在，则创建。durable = True 代表exchange持久化存储，False 非持久化存储
# channel.exchange_declare(exchange = 'test1234',durable = True, exchange_type='fanout')
# channel.exchange_declare(exchange = 'abc',durable = True, exchange_type='direct')
# for i in range(10):
#     message=json.dumps({'OrderId':"1000%s"%i})
# # 向队列插入数值 routing_key是队列名。delivery_mode = 2 声明消息在队列中持久化，delivery_mod = 1 消息非持久化。routing_key 不需要配置
#     channel.basic_publish(exchange = 'abc',routing_key = 'abc',body = message,
#                           properties=pika.BasicProperties(delivery_mode = 2))
#     print(message)
# connection.close()

connection = pika.BlockingConnection(pika.ConnectionParameters(
    host='10.60.0.221', port = 5672,virtual_host = '/test_mq',credentials = credentials))
channel = connection.channel()
channel.queue_declare(queue='abc')  # 如果队列没有创建，就创建这个队列
channel.exchange_declare(exchange = 'abcd',durable = True, exchange_type='fanout')
for i in range(10):
    message=json.dumps({'OrderId':"1000%s"%i})
    channel.basic_publish(exchange='abcd',
                      routing_key='',   # 指定队列的关键字为，这里是队列的名字
                      body=message)  # 往队列里发的消息内容

connection.close()