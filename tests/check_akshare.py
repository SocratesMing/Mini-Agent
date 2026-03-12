import akshare as ak
import pandas as pd
from datetime import datetime

# 测试不同贵金属期货
print("=== 黄金期货 au0 ===")
df = ak.futures_zh_daily_sina(symbol="au0")
print(df.head(5))

print("\n=== 白银期货 ag0 ===")
df = ak.futures_zh_daily_sina(symbol="ag0")
print(df.head(5))

print("\n=== 铂金期货 pt0 ===")
df = ak.futures_zh_daily_sina(symbol="pt0")
print(df.head(5))

print("\n=== 钯金期货 pd0 ===")
df = ak.futures_zh_daily_sina(symbol="pd0")
print(df.head(5))

# 测试日期过滤
print("\n=== 测试日期过滤 ===")
df = ak.futures_zh_daily_sina(symbol="au0")
df['date'] = pd.to_datetime(df['date'])
start_dt = datetime(2026, 2, 8)
end_dt = datetime(2026, 3, 10)
filtered = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
print(f"Filtered rows: {len(filtered)}")
print(filtered)
