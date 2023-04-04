import defibot
from web3 import Web3, eth, exceptions
import queue
import threading
import time
import json
import requests
import traceback
import base64
from defibot import tx_pb2
from defibot.curve import CurveDecoder
from defibot.slingshot import Slingshot
from defibot.routers.unknown import Unknown
import asyncio
import websockets
from websockets import connect
import pandas as pd
import numpy as np
import datetime
import pytz
from defibot.chains import ChainConfiguration



print('1: Cronos') # moved
print('2: Evmos')
print('3: Canto')


config = int(input('Select Configuration\n'))


class BotConfig:
    TradeFee = 0.0017
    Chain = 'Cronos'
    
bC = BotConfig()


if(config == 1):
    Chain = 'Cronos'
    Servers = [['https://rpc-cronos.crypto.org/unconfirmed_txs',0.3],['http://localhost:26657/unconfirmed_txs',0.1]]
    #Servers = [['http://localhost:26657/unconfirmed_txs',0.1]]
if(config == 2):
    Chain = 'Evmos'
    Servers = [['http://localhost:26657/unconfirmed_txs',0.1]]
    
if(config == 3):
    Chain = 'Canto'
    Servers = [['http://localhost:26657/unconfirmed_txs',0.1]]
    WS_Server = 'ws://127.0.0.1:31331/ws'
    
if(Chain != 'Canto'):
    uniswapv2_router_abi_file = open('defibot/abis/Uniswapv2router.json','r')
    uniswapv2_router_abi = json.load(uniswapv2_router_abi_file)
    uniswapv2_router_abi = json.loads(uniswapv2_router_abi['result'])
else:
    # uniswap2router_all_variants_Avalanche.json
    uniswapv2_router_abi_file = open('defibot/abis/uniswap2router_all_variants_Avalanche.json','r')
    uniswapv2_router_abi = json.load(uniswapv2_router_abi_file)
    
    
    
uniswapv2_router_abi_file.close()

    
bC.Chain = Chain
bC.VariableTokenName = 'PendingBotCosmos'
bC.StableTokenName = 'v4'

    
    
# Madbot
config_df = pd.read_excel('DefiBotConfigurations.xlsx',sheet_name='Madbot')
config_df = np.transpose(config_df.values)
config_df = pd.DataFrame(config_df)
config_df.columns = config_df.iloc[0]
config_df = config_df[1:]

routers_madbot = config_df[config_df['Chain']==Chain].dexRouterAddress.values

# Fraxbot

config_df = pd.read_excel('DefiBotConfigurations.xlsx',sheet_name='Fraxbot')
config_df = np.transpose(config_df.values)
config_df = pd.DataFrame(config_df)
config_df.columns = config_df.iloc[0]
config_df = config_df[1:]

routers_fraxbot1 = config_df[config_df['Chain']==Chain].dexRouterAddress.values
routers_fraxbot2 = config_df[config_df['Chain']==Chain].dexRouter_Variable_Gas.values
routers_fraxbot3 = config_df[config_df['Chain']==Chain].dexRouter_Stable_Gas.values
del config_df

router_list = list(routers_madbot) + list(routers_fraxbot1) + list(routers_fraxbot2) + list(routers_fraxbot3)
router_list = list(set(router_list))

if(np.nan in router_list):
    router_list.remove(np.nan)

r_lower = [r.lower() for r in router_list]
router_list = list(set(router_list + r_lower))

curve_routers = [
    '0xdB04E53eC3FAB887Be2F55C3fD79bC57855bC827' # MM Metapool  
    ,'0x61bB2F4a4763114268a47fB990e633Cb40f045F8' # MM basepool
    ,'0xa34C0fE36541fB085677c36B4ff0CCF5fa2B32d6' # ferro pool 1
    ,'0xC0465289ffd82cd1200e64629866da0042b9bcFe' # annex pool
    ,'0xe8d13664a42B338F009812Fa5A75199A865dA5cD' # ferro pool 2
    ,'0x43F3671b099b78D26387CD75283b826FD9585B60' # random pool
    ]

curve_routers_lower = [r.lower() for r in curve_routers]

curve_routers = curve_routers + curve_routers_lower
curve_routers = list(set(curve_routers))

router_list = router_list + curve_routers


#Servers = [['http://45.32.100.193:26657/unconfirmed_txs',0.3],['http://45.76.144.33:26657/unconfirmed_txs',0.3],['https://rpc-cronos.crypto.org/unconfirmed_txs',0.3]]



bC.dexRouterAddress = '0x145677FC4d9b8F19B5D56d1820c48e0443049a30' # MMF

bC.RPC_Servers, bC.WS_Servers, RPC_Server_init, unused = defibot.servers.GetServers(bC,bC.Chain)
 
bC.conn = Web3(Web3.HTTPProvider(RPC_Server_init, request_kwargs={'timeout': 60}))
bC.conn_init = bC.conn
ChainConfiguration(bC)

bC.swaps = queue.Queue()

hash_set = list()

curveDecoder = CurveDecoder(bC.conn)

if(Chain == 'Evmos'):
    router_list = ['0xFCd2Ce20ef8ed3D43Ab4f8C2dA13bbF1C6d9512F',
                   '0x64C3b10636baBb3Ef46a7E2E5248b0dE43198fCB',
                   '0x3Bc1F48740a5D6dffAc36FAF4c9905a941509348',
                   '0x525e3011F77019595BfB954a11876C02c0929b10']
    
if(Chain == 'Canto'):
    router_list = ['0xa252eEE9BDe830Ca4793F054B506587027825a8e',
                    '0xB6E050060C831d048e928c82151f2681D9BB8c5d',
                    '0x534cF67ff27586A07136EF3088fbdbee781Ca9b3',
                    '0x543dB6c8137c74952dA1830b6E502912608c0E69',
                    '0x0e2374110f4Eba21f396FBf2d92cC469372f7DA0',
                    '0xe6e35e2AFfE85642eeE4a534d4370A689554133c',
                    '0xe076DcC56147B72d3272b2539A36C74b3a3178f5']
    router_list += ['0x8A1d036bE71C9C4A6C3d951Cc2A3Ee028D12d3fa'] # slingshot router
    router_list += ['0xE9A2a22c92949d52e963E43174127BEb50739dcF'] # unknown router
    
    slingshot_decoder = Slingshot(bC.conn, '0x8A1d036bE71C9C4A6C3d951Cc2A3Ee028D12d3fa')
    unknown_decoder = Unknown(bC.conn, '0xE9A2a22c92949d52e963E43174127BEb50739dcF')

def TimeString():
    f = '%Y-%m-%d %H:%M:%S,%f'
    return datetime.datetime.now(pytz.timezone("Europe/Paris")).strftime(f)[:-3]

def ReportSlingShotSwap(router,data,idx,value, tx_hash, gas_price, gas_tip_cap = 0, gas_fee_cap = 0):
    global bC

    if(gas_price == 0):
        data['txtype'] = 'dynamic'
    else:
        data['txtype'] = 'legacy'
    
    data['methodName'] = 'swapExactTokensForTokens'
    data['receivedTime'] = time.time()
    data['router'] = router
    data['value'] = value
    data['hash'] = tx_hash
    data['gasPrice'] = gas_price
    data['maxPriorityFeePerGas'] = gas_tip_cap
    data['maxFeePerGas'] = gas_fee_cap
    data['protocol'] = 'Uniswap2'
    #data['gas_price'] = int(L.gas_price)
    print(f'Router: {router} Server: {idx}')
    
    print(data)
    bC.swaps.put(data)

def ReportSwap(router,swapdata,idx,value, tx_hash, gas_price, gas_tip_cap = 0, gas_fee_cap = 0):
    global bC
    data = swapdata[1]
    
    if(gas_price == 0):
        data['txtype'] = 'dynamic'
    else:
        data['txtype'] = 'legacy'
    
    data['methodName'] = type(swapdata[0]).__name__
    data['receivedTime'] = time.time()
    data['router'] = router
    data['value'] = value
    data['hash'] = tx_hash
    data['gasPrice'] = gas_price
    data['maxPriorityFeePerGas'] = gas_tip_cap
    data['maxFeePerGas'] = gas_fee_cap
    data['protocol'] = 'Uniswap2'
    #data['gas_price'] = int(L.gas_price)
    print(f'Router: {router} Server: {idx}')
    
    if(Chain == 'Canto' and 'routes' in data.keys()):
        path = list()
        for route in data['routes']:
            (_to, _from, _stable) = route
            path.append(_to)
        data['path'] = path
        del data['routes']
    
    
    print(data)
    bC.swaps.put(data)
    
    
def ReportExchange(router,fn_name,args,idx,tx_hash, gas_price, gas_tip_cap = 0, gas_fee_cap = 0):
    global bC
    
    data = args
     
    if(gas_price == 0):
        data['txtype'] = 'dynamic'
    else:
        data['txtype'] = 'legacy'
        
    data['methodName'] = fn_name
    data['receivedTime'] = time.time()
    data['router'] = router
    data['value'] = 0
    data['hash'] = tx_hash
    data['gasPrice'] = gas_price
    data['maxPriorityFeePerGas'] = gas_tip_cap
    data['maxFeePerGas'] = gas_fee_cap
    data['protocol'] = 'Curve'
    
    print(f'Curve Router: {router} Server: {idx}')
    print(data)
    bC.swaps.put(data)


async def get_encoded_pending(s):
    router_contract = bC.conn.eth.contract(bC.dexRouterAddress,abi=uniswapv2_router_abi) 
    

    async with connect(s) as ws:
        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=60*60)
            signal = time.time()
            #print(json.loads(message))
            #message = json.loads(message) 
            print(message)
            h = message[1:][:-1]
            d = base64.b64decode(h)
            _str =  d.decode('latin-1')
            res = [ele for ele in router_list if(ele in _str)]
            if(len(res) > 0):
                p = tx_pb2.MsgEthereumTx()
                   
                try:
                    idx = _str.index('MsgEthereumTx',0) + 16
                    t = d[idx:]
                    p.ParseFromString(t)
                    tx_hash = p.hash
                    print(TimeString() + ' ' + tx_hash)
                except:
                    print(f'decoding failure at MsgEthereumTx for {_str}')
                    break
                
                tx_str = p.data.value
                
                if(p.data.type_url == '/ethermint.evm.v1.DynamicFeeTx'):
                    dy = tx_pb2.DynamicFeeTx()
                    
                    try:
                        dy.ParseFromString(tx_str)
                        value = int(dy.value)
                        gas_tip_cap = int(dy.gas_tip_cap)
                        gas_fee_cap = int(dy.gas_fee_cap)
                        
                        # Uniswap
                        UniswapSuccess = False
                        try:
                            swapdata = router_contract.decode_function_input(dy.data)
                            if('swap' in type(swapdata[0]).__name__):
                                ReportSwap(res[0],swapdata,Servers.index(s),value,tx_hash, 0, gas_tip_cap, gas_fee_cap)
                                #print(swapdata)
                                
                            UniswapSuccess = True
                        except:
                            pass
                        
                        if(not(UniswapSuccess)):
                            (Success, fn_name, args) = curveDecoder.Decode(dy.data)
                            if(Success):
                                ReportExchange(res[0],fn_name,args,Servers.index(s),tx_hash, 0, gas_tip_cap, gas_fee_cap)
                        
                                
                        if(res[0] == '0x8A1d036bE71C9C4A6C3d951Cc2A3Ee028D12d3fa'): # Slingshot
                            try:
                                (fromToken, toToken, amountIn, path) = slingshot_decoder.Decode(dy.data, bC.WNetworkToken)
                                data = dict()
                                data['amountIn'] = amountIn
                                data['amountOutMin'] = 0
                                data['path'] = path
                                data['to'] = ''
                                data['deadline'] = 0
                                res[0] = '0xa252eEE9BDe830Ca4793F054B506587027825a8e'
                                ReportSlingShotSwap(res[0],data,Servers.index(s),value,tx_hash, 0, gas_tip_cap, gas_fee_cap)
                            except:
                                traceback.print_exc()
                                
                                
                        if(res[0] == '0xE9A2a22c92949d52e963E43174127BEb50739dcF'): # Unknown
                            try:
                                (amountIn, amountOutMin, path) = unknown_decoder.Decode(dy.data)
                                data = dict()
                                data['amountIn'] = amountIn
                                data['amountOutMin'] = amountOutMin
                                data['path'] = path
                                data['to'] = ''
                                data['deadline'] = 0
                                res[0] = '0xa252eEE9BDe830Ca4793F054B506587027825a8e'
                                ReportSlingShotSwap(res[0],data,Servers.index(s),value,tx_hash, 0, gas_tip_cap, gas_fee_cap)
                            except:
                                traceback.print_exc()
                                
                            
                        
                            
                            
                    except:
                        print(f'decoding failure at DynamicFeeTx for {tx_str}')
                        
                elif(p.data.type_url == '/ethermint.evm.v1.LegacyTx'):
                    L = tx_pb2.LegacyTx()
                    
                    try:
                        L.ParseFromString(p.data.value)
                        value = int(L.value)
                        gas_price = int(L.gas_price)
                        
                        # Uniswap
                        UniswapSuccess = False
                        try:
                            swapdata = router_contract.decode_function_input(L.data)
                            if('swap' in type(swapdata[0]).__name__):
                                ReportSwap(res[0],swapdata,Servers.index(s),value,tx_hash,gas_price)  
                                #print(swapdata)
                            UniswapSuccess = True
                        except:
                            pass
                        
                        if(not(UniswapSuccess)): 
                            (Success, fn_name, args) = curveDecoder.Decode(L.data)
                            if(Success):
                                ReportExchange(res[0],fn_name,args,Servers.index(s),tx_hash,gas_price)
                                
                        if(res[0] == '0x8A1d036bE71C9C4A6C3d951Cc2A3Ee028D12d3fa'): # Slingshot
                            try:
                                (fromToken, toToken, amountIn, path) = slingshot_decoder.Decode(L.data, bC.WNetworkToken)
                                data = dict()
                                data['amountIn'] = amountIn
                                data['amountOutMin'] = 0
                                data['path'] = path
                                data['to'] = ''
                                data['deadline'] = 0
                                res[0] = '0xa252eEE9BDe830Ca4793F054B506587027825a8e'
                                ReportSlingShotSwap(res[0],data,Servers.index(s),value,tx_hash, gas_price)
                            except:
                                traceback.print_exc()
                                
                                
                        if(res[0] == '0xE9A2a22c92949d52e963E43174127BEb50739dcF'): # Unknown
                            try:
                                (amountIn, amountOutMin, path) = unknown_decoder.Decode(L.data)
                                data = dict()
                                data['amountIn'] = amountIn
                                data['amountOutMin'] = amountOutMin
                                data['path'] = path
                                data['to'] = ''
                                data['deadline'] = 0
                                res[0] = '0xa252eEE9BDe830Ca4793F054B506587027825a8e'
                                ReportSlingShotSwap(res[0],data,Servers.index(s),value,tx_hash, gas_price)
                            except:
                                traceback.print_exc()
                            
                                
                    except:
                        print(f'decoding failure at LegacyTx for {tx_str}')
                        
                else:
                    print(f'Unknown tx type: {p.data.type_url}')
  
            
            
def PendingEventWatcher(s):
    print(f'Starting PendingEventWatcher for server {s}')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            #asyncio.run_in_executor(None, loop.run_until_complete, get_sync_events(s))
            loop.run_until_complete(get_encoded_pending(s))
            
        except asyncio.TimeoutError:
            time.sleep(1)
            continue
        
        except asyncio.IncompleteReadError:
            time.sleep(2)
            continue
        
        except websockets.ConnectionClosedError:
            time.sleep(2)
            continue
        
        except websockets.ConnectionClosedOK:
            time.sleep(2)
            continue
        except Exception:
            traceback.print_exc()
            time.sleep(10)
            

CLIENTS = set()

async def handler(websocket, path):
    CLIENTS.add(websocket)
    print('new connection')
    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.remove(websocket)
        
        
async def broadcast(message):
    for websocket in CLIENTS:
        asyncio.create_task(send(websocket, message))
        #await send(websocket, message)
        


async def send(websocket, message):
    try:
        await websocket.send(message)
    except websockets.ConnectionClosed:
          pass  

def broadcast_messages():
    while True:
        try:
            swap = bC.swaps.get(timeout=1)
            asyncio.run(broadcast(json.dumps(swap)))
        except queue.Empty:
            pass
      

if __name__ == '__main__':
    #threading.Thread(target=broadcast_messages,args=()).start()
    

    t = threading.Thread(target=PendingEventWatcher,args=(WS_Server,))
    t.start()
    t.join()
    
    #start_server = websockets.serve(handler, "localhost", 31337)
    #asyncio.get_event_loop().run_until_complete(start_server)
    #asyncio.get_event_loop().run_forever()