celery 是异步任务python 库，针对耗时任务进行消息队列分发，子进程处理任务，以免主任务过长等待 而不能及时响应调用者
比如 发送邮件 订单处理 视频处理等需求，我们曾经用celery redis 做过 批量生成二维码业务，定时任务管理等 

首先安装 redis 和 celery库 
1.celery 安装 
      pip install celery 
      
2.redis 安装
      参考 
      
 
 创建任务 tasks.py
 
 
broker = 'redis://localhost:6378/1'  # 中间消息队列角色 生成的消息 通过其 消费者取消息 进行消费
backend = 'redis://localhost:6378/2'  # 运行结果
app = Celery('my_task',broker=broker,backend=backend) # 创建任务对象


@app.task
def add(x,y):
    print('-----------------add --------------------')
    time.sleep(10)
    return x + y

这是一个add函数的任务，将在业务代码中调用该add函数 ，来构造一个异步的任务，调用者 直接返回 而这个业务逻辑充当生产者 生产的消息，通过broker 消费者进行消费 实行耗时的逻辑 



业务逻辑 调用代码  

import time
from tasks import add


def main():
    a1 = time.time()
    print('start task...')
    # 延时调用 调用后立即返回，消息产生 等待消费者消费该消息
    result = add.delay(10, 20)
    print('end task...')
    # 该方法是调用判断该消息的状态 只有状态为ok 才完毕 得到其结果 立即调用 一般都是 False
    print(result.ready())
    a2 = time.time()
    print('共耗时：%s' % str(a2 - a1))


if __name__ == '__main__':
    main()

以上是触发了 异步消息任务，调用add 立即返回 不会等待其处理结果 所以耗时 为0.2s

当 其word 消费消息的时候 处理这个耗时的任务 处理完会更新状态并把结果保存在redis当中(一般结果集没什么用 只需要状态就可以)




 
