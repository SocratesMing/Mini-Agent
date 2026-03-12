#!/usr/bin/env python3
"""
外汇和贵金属行情数据获取脚本
使用 akshare 库获取实时和历史外汇汇率和贵金属价格，并写入MySQL数据库

支持：
1. 实时数据获取
2. 近一个月历史数据获取
"""

import pymysql
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any
import warnings

warnings.filterwarnings('ignore')


DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "1234",
    "database": "demo",
    "charset": "utf8mb4",
}


FOREIGN_EXCHANGE_PAIRS = [
    {"symbol": "EUR/USD", "base_currency": "EUR", "quote_currency": "USD"},
    {"symbol": "GBP/USD", "base_currency": "GBP", "quote_currency": "USD"},
    {"symbol": "USD/JPY", "base_currency": "USD", "quote_currency": "JPY"},
    {"symbol": "USD/CHF", "base_currency": "USD", "quote_currency": "CHF"},
    {"symbol": "AUD/USD", "base_currency": "AUD", "quote_currency": "USD"},
    {"symbol": "USD/CAD", "base_currency": "USD", "quote_currency": "CAD"},
    {"symbol": "NZD/USD", "base_currency": "NZD", "quote_currency": "USD"},
    {"symbol": "USD/CNY", "base_currency": "USD", "quote_currency": "CNY"},
    {"symbol": "USD/HKD", "base_currency": "USD", "quote_currency": "HKD"},
    {"symbol": "USD/SGD", "base_currency": "USD", "quote_currency": "SGD"},
]

PRECIOUS_METALS = [
    {"symbol": "XAU/USD", "name": "黄金", "code": "XAU", "futures_code": "au0"},
    {"symbol": "XAG/USD", "name": "白银", "code": "XAG", "futures_code": "ag0"},
    {"symbol": "XPT/USD", "name": "铂金", "code": "XPT", "futures_code": "pt0"},
    {"symbol": "XPD/USD", "name": "钯金", "code": "XPD", "futures_code": "pd0"},
]


def create_database():
    """创建数据库"""
    config = DB_CONFIG.copy()
    database = config.pop("database")
    
    conn = pymysql.connect(**config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        conn.commit()
        print(f"数据库 {database} 创建成功")
    finally:
        conn.close()


def create_tables():
    """创建数据表"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS foreign_exchange (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL COMMENT '货币对',
                    base_currency VARCHAR(10) NOT NULL COMMENT '基础货币',
                    quote_currency VARCHAR(10) NOT NULL COMMENT '报价货币',
                    bid_price DECIMAL(18, 8) COMMENT '买入价',
                    ask_price DECIMAL(18, 8) COMMENT '卖出价',
                    mid_price DECIMAL(18, 8) COMMENT '中间价',
                    spread DECIMAL(18, 8) COMMENT '点差',
                    change_percent DECIMAL(10, 4) COMMENT '涨跌幅%',
                    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外汇实时行情'
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS foreign_exchange_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL COMMENT '货币对',
                    base_currency VARCHAR(10) NOT NULL COMMENT '基础货币',
                    quote_currency VARCHAR(10) NOT NULL COMMENT '报价货币',
                    price DECIMAL(18, 8) COMMENT '汇率',
                    change_percent DECIMAL(10, 4) COMMENT '涨跌幅%',
                    trade_date DATE NOT NULL COMMENT '交易日期',
                    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_symbol_date (symbol, trade_date),
                    INDEX idx_trade_date (trade_date),
                    INDEX idx_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外汇历史行情'
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS precious_metals (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL COMMENT '贵金属代码',
                    name VARCHAR(50) COMMENT '贵金属名称',
                    base_currency VARCHAR(10) NOT NULL COMMENT '基准货币',
                    quote_currency VARCHAR(10) NOT NULL COMMENT '报价货币',
                    bid_price DECIMAL(18, 8) COMMENT '买入价',
                    ask_price DECIMAL(18, 8) COMMENT '卖出价',
                    mid_price DECIMAL(18, 8) COMMENT '中间价',
                    spread DECIMAL(18, 8) COMMENT '点差',
                    change_percent DECIMAL(10, 4) COMMENT '涨跌幅%',
                    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='贵金属实时行情'
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS precious_metals_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL COMMENT '贵金属代码',
                    name VARCHAR(50) COMMENT '贵金属名称',
                    open_price DECIMAL(18, 8) COMMENT '开盘价',
                    high_price DECIMAL(18, 8) COMMENT '最高价',
                    low_price DECIMAL(18, 8) COMMENT '最低价',
                    close_price DECIMAL(18, 8) COMMENT '收盘价',
                    change_percent DECIMAL(10, 4) COMMENT '涨跌幅%',
                    trade_date DATE NOT NULL COMMENT '交易日期',
                    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_symbol_date (symbol, trade_date),
                    INDEX idx_trade_date (trade_date),
                    INDEX idx_symbol (symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='贵金属历史行情'
            """)
        conn.commit()
        print("数据表创建成功")
    finally:
        conn.close()


def fetch_forex_realtime() -> List[Dict[str, Any]]:
    """获取实时外汇数据 - 使用 forex_spot_em 接口"""
    data = []
    
    try:
        print("  调用 akshare forex_spot_em 接口...")
        df = ak.forex_spot_em()
        
        if df is None or df.empty:
            print("  未能获取到外汇数据")
            return data
        
        rates = {}
        for _, row in df.iterrows():
            code = str(row.get('代码', ''))
            name = str(row.get('名称', ''))
            price = row.get('最新价', 0)
            change = row.get('涨跌幅', 0)
            
            if 'USD' in code:
                currency = code.replace('USD', '').replace('CNYC', '').replace('CNY', '')
                if currency:
                    rates[currency] = {'price': float(price) if price else 0, 'change': float(change) if change else 0}
        
        print(f"  获取到 {len(rates)} 种货币汇率")
        
        for pair in FOREIGN_EXCHANGE_PAIRS:
            base = pair["base_currency"]
            quote = pair["quote_currency"]
            
            base_info = rates.get(base, {})
            quote_info = rates.get(quote, {})
            
            base_price = base_info.get('price', 1 if base == 'USD' else 0)
            quote_price = quote_info.get('price', 1 if quote == 'USD' else 0)
            
            if base_price and quote_price:
                if base == 'USD':
                    mid_price = 1 / quote_price
                elif quote == 'USD':
                    mid_price = base_price
                else:
                    usd_to_base = 1 / base_price if base_price else 0
                    usd_to_quote = 1 / quote_price if quote_price else 0
                    mid_price = usd_to_base / usd_to_quote if usd_to_quote else 0
                
                if mid_price > 0:
                    spread = mid_price * 0.001
                    
                    data.append({
                        "symbol": pair["symbol"],
                        "base_currency": base,
                        "quote_currency": quote,
                        "bid_price": round(mid_price - spread/2, 8),
                        "ask_price": round(mid_price + spread/2, 8),
                        "mid_price": round(mid_price, 8),
                        "spread": round(spread, 8),
                        "change_percent": base_info.get('change', quote_info.get('change', 0)),
                    })
                
    except Exception as e:
        print(f"  获取外汇实时数据失败: {e}")
    
    return data


def fetch_forex_history(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """获取外汇历史数据 - 使用 forex_hist_em 接口"""
    data = []
    
    try:
        print(f"  调用 akshare forex_hist_em 接口...")
        
        for pair in FOREIGN_EXCHANGE_PAIRS:
            try:
                base = pair["base_currency"]
                quote = pair["quote_currency"]
                
                symbol = f"{base}{quote}"
                df = ak.forex_hist_em(symbol=symbol)
                
                if df is not None and not df.empty:
                    df['日期'] = pd.to_datetime(df['日期'])
                    start_dt = datetime.strptime(start_date, '%Y%m%d')
                    end_dt = datetime.strptime(end_date, '%Y%m%d')
                    df = df[(df['日期'] >= start_dt) & (df['日期'] <= end_dt)]
                    
                    print(f"    {pair['symbol']}: 获取到 {len(df)} 条数据")
                    
                    for _, row in df.iterrows():
                        try:
                            date_val = row.get('日期')
                            price = row.get('最新价', row.get('收盘', 0))
                            
                            if date_val and price:
                                trade_date = date_val.date() if hasattr(date_val, 'date') else date_val
                                
                                price = float(price) if price else 0
                                
                                data.append({
                                    "symbol": pair["symbol"],
                                    "base_currency": base,
                                    "quote_currency": quote,
                                    "price": round(price, 8),
                                    "change_percent": 0,
                                    "trade_date": trade_date,
                                })
                        except Exception as e:
                            continue
                else:
                    print(f"    {pair['symbol']}: 无数据")
                    
            except Exception as e:
                print(f"    获取 {pair['symbol']} 历史数据失败: {e}")
                continue
                
    except Exception as e:
        print(f"  获取外汇历史数据失败: {e}")
    
    return data


def fetch_precious_metals_realtime() -> List[Dict[str, Any]]:
    """获取贵金属实时数据 - 使用 forex_spot_em 接口"""
    data = []
    
    try:
        print("  调用 akshare forex_spot_em 接口获取贵金属数据...")
        df = ak.forex_spot_em()
        
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                name = str(row.get('名称', ''))
                price = row.get('最新价', 0)
                change = row.get('涨跌幅', 0)
                
                if '黄金' in name or '金' in name:
                    symbol = 'XAU/USD'
                    code = 'XAU'
                elif '银' in name:
                    symbol = 'XAG/USD'
                    code = 'XAG'
                else:
                    continue
                
                price = float(price) if price else 0
                change = float(change) if change else 0
                
                if price > 0:
                    spread = price * 0.001
                    
                    data.append({
                        "symbol": symbol,
                        "name": name.replace('中间价', '').strip(),
                        "base_currency": code,
                        "quote_currency": "CNY",
                        "bid_price": round(price - spread/2, 2),
                        "ask_price": round(price + spread/2, 2),
                        "mid_price": round(price, 2),
                        "spread": round(spread, 2),
                        "change_percent": round(change, 4),
                    })
        
        if len(data) < 2:
            print("  使用备用贵金属数据...")
            
    except Exception as e:
        print(f"  获取贵金属实时数据失败: {e}")
    
    if len(data) < 2:
        metal_data = [
            {"symbol": "XAU/USD", "name": "黄金", "base_currency": "XAU", "quote_currency": "USD"},
            {"symbol": "XAG/USD", "name": "白银", "base_currency": "XAG", "quote_currency": "USD"},
            {"symbol": "XPT/USD", "name": "铂金", "base_currency": "XPT", "quote_currency": "USD"},
            {"symbol": "XPD/USD", "name": "钯金", "base_currency": "XPD", "quote_currency": "USD"},
        ]
        
        for metal in metal_data:
            if not any(d["symbol"] == metal["symbol"] for d in data):
                data.append({
                    "symbol": metal["symbol"],
                    "name": metal["name"],
                    "base_currency": metal["base_currency"],
                    "quote_currency": metal["quote_currency"],
                    "bid_price": 0,
                    "ask_price": 0,
                    "mid_price": 0,
                    "spread": 0,
                    "change_percent": 0,
                })
                
    return data


def fetch_precious_metals_history(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """获取贵金属历史数据 - 使用期货日线接口"""
    data = []
    
    try:
        print(f"  调用贵金属期货日线接口 ({start_date} - {end_date})...")
        
        for metal in PRECIOUS_METALS:
            try:
                symbol = metal["symbol"]
                name = metal["name"]
                futures_code = metal.get("futures_code", "")
                
                if not futures_code:
                    print(f"    {name}: 无期货代码")
                    continue
                
                try:
                    df = ak.futures_zh_daily_sina(symbol=futures_code)
                    if df is not None and not df.empty:
                        print(f"    {name}: 获取到 {len(df)} 条数据")
                        
                        df['date'] = pd.to_datetime(df['date'])
                        start_dt = datetime.strptime(start_date, '%Y%m%d')
                        end_dt = datetime.strptime(end_date, '%Y%m%d')
                        df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                        
                        if len(df) > 0:
                            print(f"    {name}: 筛选后 {len(df)} 条数据")
                        
                        for _, row in df.iterrows():
                            try:
                                date_val = row.get('date')
                                close_price = row.get('close', 0)
                                open_price = row.get('open', 0)
                                high_price = row.get('high', 0)
                                low_price = row.get('low', 0)
                                
                                if date_val:
                                    trade_date = date_val.date() if hasattr(date_val, 'date') else date_val
                                    
                                    change = 0
                                    if open_price and float(open_price) != 0 and close_price:
                                        change = ((float(close_price) - float(open_price)) / float(open_price) * 100)
                                    
                                    data.append({
                                        "symbol": symbol,
                                        "name": name,
                                        "open_price": round(float(open_price), 2) if open_price else 0,
                                        "high_price": round(float(high_price), 2) if high_price else 0,
                                        "low_price": round(float(low_price), 2) if low_price else 0,
                                        "close_price": round(float(close_price), 2) if close_price else 0,
                                        "change_percent": round(change, 4),
                                        "trade_date": trade_date,
                                    })
                            except Exception as e:
                                continue
                    else:
                        print(f"    {name}: 无数据")
                except Exception as e:
                    print(f"    {name}: 获取失败 - {e}")
                    continue
                    
            except Exception as e:
                print(f"    获取 {metal['name']} 历史数据失败: {e}")
                continue
                
    except Exception as e:
        print(f"  获取贵金属历史数据失败: {e}")
    
    return data


def insert_forex_realtime(data: List[Dict[str, Any]]):
    """插入外汇实时数据"""
    if not data:
        print("没有外汇实时数据需要插入")
        return
        
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO foreign_exchange 
                (symbol, base_currency, quote_currency, bid_price, ask_price, mid_price, spread, change_percent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                bid_price = VALUES(bid_price),
                ask_price = VALUES(ask_price),
                mid_price = VALUES(mid_price),
                spread = VALUES(spread),
                change_percent = VALUES(change_percent),
                update_time = CURRENT_TIMESTAMP
            """
            
            for item in data:
                cursor.execute(sql, (
                    item["symbol"],
                    item["base_currency"],
                    item["quote_currency"],
                    item["bid_price"],
                    item["ask_price"],
                    item["mid_price"],
                    item["spread"],
                    item["change_percent"],
                ))
                
        conn.commit()
        print(f"成功插入/更新 {len(data)} 条外汇实时数据")
    finally:
        conn.close()


def insert_forex_history(data: List[Dict[str, Any]]):
    """插入外汇历史数据"""
    if not data:
        print("没有外汇历史数据需要插入")
        return
    
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE foreign_exchange_history")
            
            sql = """
                INSERT INTO foreign_exchange_history 
                (symbol, base_currency, quote_currency, price, change_percent, trade_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                price = VALUES(price),
                change_percent = VALUES(change_percent),
                update_time = CURRENT_TIMESTAMP
            """
            
            for item in data:
                cursor.execute(sql, (
                    item["symbol"],
                    item["base_currency"],
                    item["quote_currency"],
                    item["price"],
                    item["change_percent"],
                    item["trade_date"],
                ))
                
        conn.commit()
        print(f"成功插入/更新 {len(data)} 条外汇历史数据")
    finally:
        conn.close()


def insert_precious_metals_realtime(data: List[Dict[str, Any]]):
    """插入贵金属实时数据"""
    if not data:
        print("没有贵金属实时数据需要插入")
        return
        
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO precious_metals 
                (symbol, name, base_currency, quote_currency, bid_price, ask_price, mid_price, spread, change_percent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                bid_price = VALUES(bid_price),
                ask_price = VALUES(ask_price),
                mid_price = VALUES(mid_price),
                spread = VALUES(spread),
                change_percent = VALUES(change_percent),
                update_time = CURRENT_TIMESTAMP
            """
            
            for item in data:
                cursor.execute(sql, (
                    item["symbol"],
                    item["name"],
                    item["base_currency"],
                    item["quote_currency"],
                    item["bid_price"],
                    item["ask_price"],
                    item["mid_price"],
                    item["spread"],
                    item["change_percent"],
                ))
                
        conn.commit()
        print(f"成功插入/更新 {len(data)} 条贵金属实时数据")
    finally:
        conn.close()


def insert_precious_metals_history(data: List[Dict[str, Any]]):
    """插入贵金属历史数据"""
    if not data:
        print("没有贵金属历史数据需要插入")
        return
        
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE TABLE precious_metals_history")
            
            sql = """
                INSERT INTO precious_metals_history 
                (symbol, name, open_price, high_price, low_price, close_price, change_percent, trade_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_price = VALUES(close_price),
                change_percent = VALUES(change_percent),
                update_time = CURRENT_TIMESTAMP
            """
            
            for item in data:
                cursor.execute(sql, (
                    item["symbol"],
                    item["name"],
                    item["open_price"],
                    item["high_price"],
                    item["low_price"],
                    item["close_price"],
                    item["change_percent"],
                    item["trade_date"],
                ))
                
        conn.commit()
        print(f"成功插入/更新 {len(data)} 条贵金属历史数据")
    finally:
        conn.close()


def fetch_realtime():
    """获取实时数据"""
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始获取实时行情数据...")
    
    print("\n获取外汇实时数据...")
    forex_data = fetch_forex_realtime()
    print(f"获取到 {len(forex_data)} 条外汇实时数据")
    
    print("\n获取贵金属实时数据...")
    metals_data = fetch_precious_metals_realtime()
    print(f"获取到 {len(metals_data)} 条贵金属实时数据")
    
    print("\n保存实时数据到数据库...")
    insert_forex_realtime(forex_data)
    insert_precious_metals_realtime(metals_data)
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 实时数据更新完成!")


def fetch_history():
    """获取近一个月历史数据"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    start_str = start_date.strftime('%Y%m%d')
    end_str = end_date.strftime('%Y%m%d')
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始获取近一个月历史数据...")
    print(f"日期范围: {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}")
    
    print("\n获取外汇历史数据...")
    forex_history = fetch_forex_history(start_str, end_str)
    print(f"获取到 {len(forex_history)} 条外汇历史数据")
    
    print("\n获取贵金属历史数据...")
    metals_history = fetch_precious_metals_history(start_str, end_str)
    print(f"获取到 {len(metals_history)} 条贵金属历史数据")
    
    print("\n保存历史数据到数据库...")
    insert_forex_history(forex_history)
    insert_precious_metals_history(metals_history)
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 历史数据更新完成!")


def show_realtime_data():
    """显示实时数据"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        print("\n" + "="*60)
        print("外汇实时行情:")
        print("="*60)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT symbol, mid_price, spread, change_percent, update_time FROM foreign_exchange ORDER BY symbol")
            rows = cursor.fetchall()
            print(f"{'货币对':<15} {'中间价':<15} {'点差':<12} {'涨跌幅%':<10} {'更新时间'}")
            print("-"*60)
            for row in rows:
                print(f"{row['symbol']:<15} {row['mid_price']:<15.4f} {row['spread']:<12.4f} {row['change_percent']:<10.2f} {row['update_time']}")
        
        print("\n" + "="*60)
        print("贵金属实时行情:")
        print("="*60)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT symbol, name, mid_price, spread, change_percent, update_time FROM precious_metals ORDER BY symbol")
            rows = cursor.fetchall()
            print(f"{'代码':<12} {'名称':<12} {'中间价':<15} {'点差':<12} {'涨跌幅%':<10} {'更新时间'}")
            print("-"*70)
            for row in rows:
                print(f"{row['symbol']:<12} {row['name']:<12} {row['mid_price']:<15.2f} {row['spread']:<12.2f} {row['change_percent']:<10.2f} {row['update_time']}")
    finally:
        conn.close()


def show_history_data():
    """显示历史数据"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        print("\n" + "="*60)
        print("外汇历史行情 (最近30天):")
        print("="*60)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT symbol, price, change_percent, trade_date 
                FROM foreign_exchange_history 
                ORDER BY symbol, trade_date DESC 
                LIMIT 50
            """)
            rows = cursor.fetchall()
            print(f"{'货币对':<15} {'汇率':<15} {'涨跌幅%':<10} {'日期'}")
            print("-"*50)
            for row in rows:
                print(f"{row['symbol']:<15} {row['price']:<15.4f} {row['change_percent']:<10.2f} {row['trade_date']}")
        
        print("\n" + "="*60)
        print("贵金属历史行情 (最近30天):")
        print("="*60)
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT symbol, name, close_price, change_percent, trade_date 
                FROM precious_metals_history 
                ORDER BY symbol, trade_date DESC 
                LIMIT 50
            """)
            rows = cursor.fetchall()
            print(f"{'代码':<12} {'名称':<8} {'收盘价':<15} {'涨跌幅%':<10} {'日期'}")
            print("-"*50)
            for row in rows:
                print(f"{row['symbol']:<12} {row['name']:<8} {row['close_price']:<15.2f} {row['change_percent']:<10.2f} {row['trade_date']}")
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    print("外汇和贵金属行情数据获取脚本 (akshare版)")
    print("="*60)
    
    create_database()
    create_tables()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--realtime":
            fetch_realtime()
            show_realtime_data()
        elif sys.argv[1] == "--history":
            fetch_history()
            show_history_data()
        elif sys.argv[1] == "--show":
            show_realtime_data()
            show_history_data()
        else:
            print("用法:")
            print("  python fetch_market_data.py --realtime   仅获取实时数据")
            print("  python fetch_market_data.py --history    仅获取历史数据")
            print("  python fetch_market_data.py --show       显示所有数据")
    else:
        fetch_realtime()
        show_realtime_data()
        
        fetch_history()
        show_history_data()
