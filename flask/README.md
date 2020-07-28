flask介绍

flask 是轻量级python  web 框架 ，简单到只需要 一个文件就可以启动一个信息管理系统，但是flask 并不是只能针对小项目实现，大型项目也可以使用flask  flask 提供的插件方式，丰富了整个业态，包括 db 缓存 消息队列 权限等 五花八门，相比于django这样的优势 可以灵活扩展，简单易用，相较于 tornado 的异步非阻塞的区别在于 不提供webserver 服务 使用uwsgi 做为替代，并不能支持异步非阻塞的特性 但是可以使用gevent 等框架 部署 来做到异步非阻塞

首先说明一下 普通的python 应用 在启动后 是无法对外提供应用服务的，因为一个交互过程是需要又浏览器或者客户端 发起请求 经过dns tcp  请求连接到 webserver 又webserver 服务器对网络数据 进行读写 之后 需要构造request 和 start_response 的app 来调用python app  没有 这个 过程 就无法直接通讯，这个就是wsgi 统一网关接口，而tornado自己实现了 webserver  django flask 等框架需要依赖uwsgi 来实现 flask 默认实现类库是 werkzeug 

flask 主流程分析 梳理 
一般来讲 我们都会在app.py 里开始我们的flask 应用服务的启动

import flask

app = flask.Flask(__name__)

@app.route("/")
def hello():
    return "Hello World!"

if __name__ == "__main__":
    app.run()
    
第一 创建app 对象，通过参数创建app ，主要是一些跟静态页面的一些初始化等工作 

第二 注册路由功能，通过装饰器将将注册的相应函数 以及路由规则 注册到flask 的全局变量中以进行后续匹配，信息保存到 view_functions 全局变量中

第三 运行app应用，调用app.py 的run方法 接着讲 port address 等参数 传递给 werkzeug.serving.run_simple来运行服务，并监听网络构造request start_resonse 

第四 run_simple运行，创建server 启动线程提供网络服务server，等待客户端连接，注册 相关事件 读写异常事件 使用selectors 来进行监听网络请求，当存在读事件，调用读回调函数，读取网络数据构造header 解析header 根据method 调用do_get 或者 do_post函数  最终根据环境配置 一般来讲是 调用WSGIRequestHandler的run_wsgi 来处理请求

第五 run_wsgi 函数是 最终建立和app python 业务逻辑的核心 首先 execute 来 实现 刚才创建的flask app 调用 传递的参数是request start_resonse  ，构造好environ 传递start_resonse回调函数 调用app__call__ 函數，函数 调用wsgi_app 

第六 wsgi_app 函数会根据 environ 来构造上下文环境 然后将该上下文环境压入flask 构造的栈结构 _request_ctx_stack 其实现就是一个全局字典来保存上下文对象，作用就是保存每一个连接请求的对象信息，所以在flask中  业务函数中 request 不像 django  tornado 是局别对象  而flask 是全局对象 ，因为有栈的存在 所以会保证连接隔离 ，之后调用 full_dispatch_request 

第七 full_dispatch_request函数 处理转发请求 构造返回响应对象 ，处理pre post 函数逻辑 调用dispatch_request函数 分发请求 从栈中取出上下文对象，根据上下文对象定位全局view_functions 变量来调用业务处理函数，业务处理函数调用会返回业务数据，或页面 或直接的json数据 

第八 通过返回的数据 和 environ  来构造header body  将 其写入到网络中 最后 完成整个请求处理



flask 的上下文 比较重要的理解flask 的对象 分好几种 有时间在分析下





