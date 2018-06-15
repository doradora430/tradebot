#!/usr/bin/python3
# coding: utf-8
# Dotenkun for BitMEX Ver. 1.0.2
import requests
import datetime
import time
import ccxt
import pybitflyer
import logging

HIGH  = 2            # cryptowatchから取得するJSONデータの2番目が高値であるため定数として事前定義
LOW   = 3            # cryptowatchから取得するJSONデータの3番目が安値であるため定数として事前定義
LOT   = 100          # 1度に売買する数量(ドル @BitMEX or BTC @bitFlyer)
SLEEP = 30           # ループの待ち時間
EXCHANGE     = 'MEX' # 売買対象の取引所
IS_BF_WATCH  = True  # bitFlyerのチャネル情報を売買判断に利用するかのフラグ
IS_MEX_WATCH = True  # BitMEXのチャネル情報を売買判断に利用するかのフラグ

bitmex = ccxt.bitmex({
    'apiKey': 'API-KEY',     # ご自身のAPIキー
    'secret': 'API-SECRET',  # ご自身のAPIシークレット
})

bitflyer = pybitflyer.API(
   api_key    = 'API-KEY',   # ご自身のAPIキー
   api_secret = 'API-SECRET' # ご自身のAPIシークレット
)

def mex_limit(side, price, size): # 指値発注用の関数(コード内では使用していないため単なる参考)
    o = bitmex.create_order('BTC/USD', type='limit', side=side, amount=size, price=price)
    logger.info(o['info']['ordType'] + ' ' + o['info']['side'] + ' ' + str(o['info']['orderQty']) + ' @ ' + str(o['info']['price']) + ' ' + o['id'])

def mex_market(side, size): # 成行発注用の関数
    o = bitmex.create_order('BTC/USD', type='market', side=side, amount=size)
    logger.info(o['info']['ordType'] + ' ' + o['info']['side'] + ' ' + str(o['info']['orderQty']) + ' ' + o['id'])

def bf_market(side, size): # 成行発注用の関数
    logger.info(bitflyer.sendchildorder(product_code="FX_BTC_JPY", child_order_type="MARKET", minute_to_expire= 60, side=side, size=size))

def mex_position(): # 保有ポジションの方向・数量・参入価格を取得する関数
    pos = bitmex.private_get_position()
    if pos == []:
        pos = { 'currentQty': 0, 'avgEntryPrice': 0}
    else:
        pos = pos[0]
    if pos['currentQty'] == 0: # sizeが0より大きければ現在LONG状態、0より小さければ現在SHORT状態と判断
        side = 'NO POSITION'
    elif pos['currentQty'] > 0:
        side = 'LONG'
    else:
        side = 'SHORT'
    return {'side': side, 'size': round(pos['currentQty']), 'avgEntryPrice': pos['avgEntryPrice']}

def bf_position(): # 保有ポジションの方向と数量を取得する関数(pnlは特に利用しないため削っても可)
    poss = bitflyer.getpositions(product_code="FX_BTC_JPY")
    size= pnl = 0
    for p in poss:
        if p['side'] == 'BUY':
            size += p['size']
            pnl += p['pnl']
        if p['side'] == 'SELL':
            size -= p['size']
            pnl -= p['pnl']
    if size == 0: # sizeが0以上現在LONG状態、0以下なら現在SHORT状態と判断
        side = 'NO POSITION'
    elif size > 0:
        side = 'LONG'
    else:
        side = 'SHORT'
    return {'side':side, 'size':size, 'pnl':pnl}

def mex_channel(ohlcv): # High-Lowチャネルを取得するための関数
    LEN = 18 # 期間指定18(現在の1時間足を含めず過去18時間)
    c_h = 0
    c_l  = 10000000
    for i in range(LEN): # [-2]から[-19]までの最高値・最安値を計算([-1]が最新1時間足)
        if(ohlcv['h'][-i-2] > c_h):
            c_h = ohlcv['h'][-i-2]
        if(ohlcv['l'][-i-2] < c_l):
            c_l = ohlcv['l'][-i-2]
    return {'high': c_h, 'low': c_l}

def bf_channel(ohlcv): # High-Lowチャネルを取得するための関数
    LEN = 18 # 期間指定18(現在の1時間足を含めず過去18時間)
    c_h = 0
    c_l  = 10000000
    for i in range(LEN): # [-2]から[-19]までの最高値・最安値を計算([-1]が最新1時間足)
        if(ohlcv[-i-2][HIGH] > c_h):
            c_h = ohlcv[-i-2][HIGH]
        if(ohlcv[-i-2][LOW] < c_l):
            c_l = ohlcv[-i-2][LOW]
    return {'high': c_h, 'low': c_l}

logger = logging.getLogger('LoggingTest')
logger.setLevel(10)
sh = logging.StreamHandler() # コンソール画面出力設定
logger.addHandler(sh)
fh = logging.FileHandler('dotenkun_' + EXCHANGE.lower() + '_'+str(datetime.date.today())+'.log') # ログファイル出力設定
logger.addHandler(fh)
formatter = logging.Formatter('%(asctime)s:%(lineno)d: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
sh.setFormatter(formatter)
fh.setFormatter(formatter)

logger.info('========== Dotenkun Start! ==========')
while True:
    try:
        logger.removeHandler(fh)
        fh = logging.FileHandler('dotenkun_' + EXCHANGE.lower() + '_'+str(datetime.date.today())+'.log') # ログファイル出力設定
        logger.addHandler(fh)
        fh.setFormatter(formatter)
        
        if EXCHANGE == 'MEX':
            pos = mex_position()
        elif EXCHANGE == 'BF':
            pos = bf_position()
        
        now = datetime.datetime.now().strftime('%s') # 現在時刻の取得
        r = requests.get('https://www.bitmex.com/api/udf/history?symbol=XBTUSD&resolution=60&from=' + 
        str(int(now)-3600*100) + '&to=' + now) # 過去100時間分の過去データ取得
        mex_ohlcv = r.json()                # JSONデータをリストに変換
        mex_high = round(mex_channel(mex_ohlcv)['high'], 1) # 計算したHLチャネル上限
        mex_low  = round(mex_channel(mex_ohlcv)['low'],  1) # 計算したHLチャネル下限
        mex_last = bitmex.fetch_ticker('BTC/USD')['last'] # 最終取引価格の取得

        # 直近の1時間足データが取れているかの確認のため3本分の情報を出力、また、HLチャネル情報・ポジション情報も出力
        logger.info('MEX ' + str(datetime.datetime.fromtimestamp(mex_ohlcv['t'][-4])) + ' :' + str(mex_ohlcv['h'][-4]) + '>' + str(mex_ohlcv['l'][-4]))
        logger.info('MEX ' + str(datetime.datetime.fromtimestamp(mex_ohlcv['t'][-3])) + ' :' + str(mex_ohlcv['h'][-3]) + '>' + str(mex_ohlcv['l'][-3]))
        logger.info('MEX ' + str(datetime.datetime.fromtimestamp(mex_ohlcv['t'][-2])) + ' :' + str(mex_ohlcv['h'][-2]) + '>' + str(mex_ohlcv['l'][-2]))
        logger.info('MEX ' + str(mex_high) + '>' + str(mex_low))

        r = requests.get('https://api.cryptowat.ch/markets/bitflyer/btcfxjpy/ohlc?periods=3600')
        json = r.json()                 # JSONデータをリストに変換
        bf_ohlcv = json['result']['3600']  # リストから1時間足の結果を取得
        bf_high = bf_channel(bf_ohlcv)['high'] # 計算したHLチャネル上限
        bf_low  = bf_channel(bf_ohlcv)['low']  # 計算したHLチャネル下限
        bf_last = round(bitflyer.ticker(product_code="FX_BTC_JPY")['ltp']) # 最終取引価格の取得

        # 直近の1時間足データが取れているかの確認のため3本分の情報を出力、また、HLチャネル情報・ポジション情報も出力
        logger.info('bF  ' + str(datetime.datetime.fromtimestamp(bf_ohlcv[-4][0] - 60 * 60)) + ' :' + str(bf_ohlcv[-4][HIGH]) + '>' + str(bf_ohlcv[-4][LOW]))
        logger.info('bF  ' + str(datetime.datetime.fromtimestamp(bf_ohlcv[-3][0] - 60 * 60)) + ' :' + str(bf_ohlcv[-3][HIGH]) + '>' + str(bf_ohlcv[-3][LOW]))
        logger.info('bF  ' + str(datetime.datetime.fromtimestamp(bf_ohlcv[-2][0] - 60 * 60)) + ' :' + str(bf_ohlcv[-2][HIGH]) + '>' + str(bf_ohlcv[-2][LOW]))
        logger.info('bF  ' + 'allowance=' + str(json['allowance']['remaining']) + ':' + str(bf_high) + '>' + str(bf_low))
        
        if EXCHANGE == 'MEX':
            p = 'POS :' + pos['side'] + ' ' + str(pos['size']) + ' @ ' + str(pos['avgEntryPrice'])
        elif EXCHANGE == 'BF':
            p = 'POS :' + pos['side'] + ' ' + str(pos['size'])
        logger.info(p)
        
        logger.info('終値 :$' + '{:,}'.format(mex_last) + ' (\' + '{:,}'.format(bf_last) + ')') # 最終価格
        logger.info('L価格:$' + '{:,}'.format(mex_high) + ' (\' + '{:,}'.format(bf_high) + ')') # ドテンするLong価格
        logger.info('S価格:$' + '{:,}'.format(mex_low)  + ' (\' + '{:,}'.format(bf_low)  + ')') # ドテンするShort価格
        
        # 最終取引価格がチャネル上限を超えており現在LONGポジション以外ならLONG発注
        if (mex_last > mex_high or not IS_MEX_WATCH) and (bf_last > bf_high or not IS_BF_WATCH) and pos['side'] != 'LONG':
            logger.info('Doten Long!')
            if EXCHANGE == 'MEX':
                mex_market('buy', LOT - pos['size'])
            elif EXCHANGE == 'BF':
                bf_market('BUY', LOT - pos['size'])
            time.sleep(30) # 2度同じ売買を繰り返さないため注文が通るまで30秒待つ
        # 最終取引価格がチャネル下限を割っており現在SHORTポジション以外ならSHORT発注
        elif (mex_last < mex_low or not IS_MEX_WATCH) and (bf_last < bf_low or not IS_BF_WATCH) and pos['side'] != 'SHORT':
            logger.info('Doten Short!')
            if EXCHANGE == 'MEX':
                mex_market('sell', LOT + pos['size'])
            elif EXCHANGE == 'BF':
                bf_market('SELL', LOT + pos['size'])
            time.sleep(30) # 2度同じ売買を繰り返さないため注文が通るまで30秒待つ

        time.sleep(SLEEP) # SLEEPで指定した時間(秒)だけ待ち、その後ループ(繰り返し)

    except Exception as x:
        logger.info("Error!")
        logger.exception(x)
        time.sleep(5)