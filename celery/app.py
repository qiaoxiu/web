import time
from tasks import add


def main():
    a1 = time.time()
    print('start task...')
    result = add.delay(10, 20)       
    print('end task...')
    #import pdb;pdb.set_trace()
    print(result.ready())
    a2 = time.time()
    print('共耗时：%s' % str(a2 - a1))


if __name__ == '__main__':
    main()

