import pandas as pd
url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip"
try:
    df = pd.read_csv(url, skiprows=4, index_col=0)
    df.index = pd.to_datetime(df.index.astype(str), format='%Y%m%d', errors='coerce')
    df = df.dropna()
    print("SUCCESS")
    print(df.tail())
except Exception as e:
    import traceback
    traceback.print_exc()
