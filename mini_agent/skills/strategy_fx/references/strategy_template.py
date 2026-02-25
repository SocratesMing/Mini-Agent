"""
    策略模板 - 外汇量化交易策略
    本模板提供标准化的策略开发框架
"""
import json
import os
import time

import talib as ta

import quantapi.base as base
import quantapi.md as md
import quantapi.param as param
from cqfnlib import *

# ============================================
# 策略基本信息
# ============================================
strategy_name = "Template_Strategy"  # 策略名称


# ============================================
# 策略参数类
# ============================================
class Param:
    """
    策略参数配置类
    """
    def __init__(self):
        # 基础参数
        self.symbol = param.get('策略合约')  # 交易品种
        self.source = param.get('合约渠道')  # 行情数据源
        self.bar_frequency = param.get('bar数据频率')  # K线周期
        self.lot = param.get('下单量') if param.get('下单量') is not None else 10000  # 下单量

        # 风控参数
        self.tp = param.get('止盈点数') if param.get('止盈点数') is not None else 1000  # 止盈点数
        self.sl = param.get('止损点数') if param.get('止损点数') is not None else 300  # 止损点数
        self.sp = param.get('价差点数') if param.get('价差点数') is not None else 50  # 价差点数

        # 高级功能开关
        self.protect_flag = True if param.get('推平保护开关') == "开" else False  # 推平保护
        self.move_flag = True if param.get('移动止损开关') == "开" else False  # 移动止损


# ============================================
# 初始化函数
# ============================================
def init(context):
    """
    初始化方法 - 在回测和实时模拟交易启动时触发一次

    Args:
        context: 策略上下文对象
    """
    # 记录版本信息
    version_info = "v1_0001"
    version_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
    qlog.info_f("[init] 策略: {} 初始化完成, 版本: {} ", strategy_name, version_time + "_" + version_info)

    # 初始化参数
    context.param = Param()

    # 初始化状态变量
    context.bar_last_time = None  # 最新bar时间
    context.start_k_num = 50  # 启动所需最小K线数
    context.k_num_flag = False  # K线缓存是否满足要求

    # 获取合约信息
    symbol_info = base.get_contract(context.param.symbol)
    context.digits = symbol_info['noDecimal']  # 价格小数位数
    context.point = eval(f'1e-{context.digits}')  # 最小价格单位

    # 滑点设置
    context.slippage_open = 20 * context.point  # 开仓滑点
    context.slippage_close = 500 * context.point  # 平仓滑点

    # 止盈止损设置
    context.sl = context.param.sl  # 止损点数
    context.tp = context.param.tp  # 止盈点数
    context.sp = context.param.sp  # 价差点数

    # 订单与持仓缓存
    context.sl_id = {}  # 订单ID -> 止损价
    context.tp_id = {}  # 订单ID -> 止盈价
    context.openid_closeid = {}  # 开仓单 -> 平仓单
    context.closeid_openid = {}  # 平仓单 -> 开仓单
    context.tc = TradeCount(context)  # 持仓统计

    # 推平保护设置
    context.protect_flag = context.param.protect_flag
    context.protect_point = 300  # 触发推平保护的盈利点数
    context.protect_move_point = 100  # 推平后移动到的点差

    # 移动止损设置
    context.move_flag = context.param.move_flag
    context.start_move_sl = 250  # 启动移动止损的盈利点数
    context.move_point_sl = 300  # 移动止损的点差

    # 数据统计
    context.data = {}
    context.all_open = True  # 开仓开关


# ============================================
# 策略主逻辑
# ============================================
def onData(context, data):
    """
    tick行情数据回调 - 策略核心逻辑

    Args:
        context: 策略上下文
        data: tick行情数据列表

    Note:
        data格式: [{'status': '1', 'source': 'CFETS_LC', 'type': 'ODM_DEPTH',
                   'symbol': 'EURUSDSP', 'time': 1532000820300,
                   'bestBid': 1.16478, 'bestBidAmt': 57,
                   'bestAsk': 1.1649, 'bestAskAmt': 57, ...}]
    """
    # 1. 获取K线数据
    bar = md.query_bars_pro(
        context.param.symbol,
        context.param.bar_frequency,
        context.param.source,
        count=100,
        fields=['time', 'close', 'high', 'low', 'open']
    )

    # 2. 检查数据有效性
    if bar is None or len(bar['close']) < context.start_k_num + 1:
        return

    # 3. 缓存市价信息
    bid_ask_cache(context, data[0])

    # 4. 平仓处理
    close(context)

    # 5. 检查K线时间更新
    if not check_bar_time(context, bar):
        return

    # 6. 获取历史数据
    close_arr = bar['close']
    high_arr = bar['high']
    low_arr = bar['low']
    open_arr = bar['open']

    # 7. 获取当前和前一根K线数据
    close_price1 = close_arr[-2]
    open_price1 = open_arr[-2]
    high_price1 = high_arr[-2]
    low_price1 = low_arr[-2]

    # 8. 计算技术指标
    # --- 趋势指标 ---
    ma_short = ta.MA(close_arr, timeperiod=10)
    ma_long = ta.MA(close_arr, timeperiod=30)
    ema_short = ta.EMA(close_arr, timeperiod=10)
    ema_long = ta.EMA(close_arr, timeperiod=30)

    # --- 动量指标 ---
    rsi = ta.RSI(close_arr, timeperiod=14)
    cci = ta.CCI(high_arr, low_arr, close_arr, timeperiod=14)

    # --- 波动率指标 ---
    boll_up, boll_mid, boll_low = ta.BBANDS(close_arr, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    atr = ta.ATR(high_arr, low_arr, close_arr, timeperiod=14)

    # --- MACD指标 ---
    macd, macd_signal, macd_hist = ta.MACD(close_arr)

    # ============================================
    # 9. 策略逻辑 - 多头入场条件
    # ============================================
    if context.tc.buy_num < 1 and context.all_open:
        # 示例条件: RSI超卖 + 价格突破布林下轨
        # 替换为实际策略条件
        buy_condition = (
            rsi[-2] < 30 and
            close_price1 > boll_low[-1]
        )

        if buy_condition:
            # 执行做多
            open_price = round(context.ask + context.slippage_open, context.digits)
            sl_price = round(context.ask - context.sl * context.point, context.digits)
            open_buy(context, open_price, sl_price=sl_price, tp_price=None)
            qlog.info_f("[多头入场] 价格: {}, RSI: {}, 布林下轨: {}",
                       close_price1, rsi[-2], boll_low[-1])
            return

    # ============================================
    # 10. 策略逻辑 - 空头入场条件
    # ============================================
    if context.tc.sell_num < 1 and context.all_open:
        # 示例条件: RSI超买 + 价格突破布林上轨
        # 替换为实际策略条件
        sell_condition = (
            rsi[-2] > 70 and
            close_price1 < boll_up[-1]
        )

        if sell_condition:
            # 执行做空
            open_price = round(context.bid - context.slippage_open, context.digits)
            sl_price = round(context.bid + context.sl * context.point, context.digits)
            open_sell(context, open_price, sl_price=sl_price, tp_price=None)
            qlog.info_f("[空头入场] 价格: {}, RSI: {}, 布林上轨: {}",
                       close_price1, rsi[-2], boll_up[-1])
            return


# ============================================
# 订单回调
# ============================================
def onOrder(context, order):
    """
    订单状态变化回调

    Args:
        context: 策略上下文
        order: 订单信息

    Note:
        order['orderStatus']状态码:
        0-初始化, 1-运行中, 2-订单拒绝, 5-订单超时,
        6-撤销中, 7-已撤销, 8-已结束, 9-已提交, 99-未明
    """
    qlog.info_f("[OnOrder] 订单状态变化: {}", order)

    # 更新持仓统计
    context.tc = TradeCount(context)

    # 处理平仓订单
    if order['id'] in context.closeid_openid.keys():
        if order['orderStatus'] == '8':  # 平仓完成
            open_id = context.closeid_openid[order['id']]
            del context.openid_closeid[open_id]
            del context.closeid_openid[order['id']]
            qlog.info('[OnOrder] 平仓单处理完成, 开仓单ID: {}', open_id)
        elif order['orderStatus'] == '7':  # 平仓单撤销
            open_id = context.closeid_openid[order['id']]
            del context.closeid_openid[order['id']]
            context.openid_closeid[open_id]['close_id'] = 0
            qlog.info('[OnOrder] 平仓单已撤销, 等待重新挂单')


# ============================================
# 成交回调
# ============================================
def onTrade(context, trade):
    """
    成交事件回调

    Args:
        context: 策略上下文
        trade: 成交信息
    """
    qlog.info_f("[OnTrade] 成交回报: {}", trade)


# ============================================
# 定时任务
# ============================================
def onTime(context, time, name):
    """
    定时任务回调

    Args:
        context: 策略上下文
        time: 当前时间
        name: 任务名称
    """
    pass


# ============================================
# 切日回调
# ============================================
def onBusinessDate(context, data):
    """
    切日事件回调

    Args:
        context: 策略上下文
        data: 日期数据
    """
    qlog.info_f("[OnBusinessDate] 新的交易日: {}", data)


# ============================================
# 监控回调
# ============================================
def onMonitor(context, data):
    """
    接口链路启停回调

    Args:
        context: 策略上下文
        data: 监控数据
    """
    pass


# ============================================
# 主函数入口 (本地测试用)
# ============================================
if __name__ == '__main__':
    # 本地测试代码
    from quantapi.start import start_backtest

    # 加载配置
    with open("config.json", "r", encoding="utf-8") as f:
        params = json.load(f)

    # 启动回测
    # start_backtest(strategy_name, params, back_log_level="INFO")
    # start_backtest(strategy_name, params, back_log_level="INFO", mode="OPT", optuna=True, trails=10)

    print("策略模板加载完成")
