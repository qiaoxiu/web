import pika
credentials = pika.PlainCredentials('admin', '123456')  # mq用户名和密码
connection = pika.BlockingConnection(pika.ConnectionParameters(
    host='10.60.0.221', port = 5672,virtual_host = '/test_mq',credentials = credentials))
channel = connection.channel()

channel.queue_declare(queue='abc1')  # 如果队列没有创建，就创建这个队列
channel.queue_declare(queue='abc2')  # 如果队列没有创建，就创建这个队列
channel.queue_declare(queue='abc3')  # 如果队列没有创建，就创建这个队列
channel.queue_declare(queue='abc4')  # 如果队列没有创建，就创建这个队列
channel.exchange_declare(exchange = 'abcd',durable = True,exchange_type='fanout')
channel.queue_bind(exchange = 'abcd',queue = 'abc1')
channel.queue_bind(exchange = 'abcd',queue = 'abc2')
channel.queue_bind(exchange = 'abcd',queue = 'abc3')
channel.queue_bind(exchange = 'abcd',queue = 'abc4')
def callback(ch, method, properties, body):
    print('asdasdasd')
    ch.basic_ack(delivery_tag = method.delivery_tag)
    print(body.decode())


channel.basic_consume('abc3',callback,# 设置成 False，在调用callback函数时，未收到确认标识，消息会重回队列。True，无论调用callback成功与否，消息都被消费掉
                      auto_ack = False)

print(' [*] Waiting for message. To exit press CTRL+C')
channel.start_consuming()