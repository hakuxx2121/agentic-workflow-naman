import pandas as pd, numpy as np
TARGET={"SPY":(742.23,734.59),"COIN":(138.26,133.90),"AVGO":(311.5,302.75),"MSFT":(532.5,524.5),"AMZN":(263.56,258.53),"AAPL":(341.70,338.31),"GOOGL":(290.45,284.6),"META":(622.2,606.7)}
def load(t):
    d=pd.read_csv(f"data/{t}_1m.csv",index_col=0)
    d.index=pd.to_datetime(d.index,utc=True).tz_convert("America/New_York")
    return d
def rth(d):
    return d.between_time("09:30","15:59")
