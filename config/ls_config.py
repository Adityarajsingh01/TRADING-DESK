# config/ls_config.py
# Lightstreamer connection config — TT/Hertshten market data
# ─────────────────────────────────────────────────────────────────────────────
# Library : lightstreamer-client-lib  (official SDK)
#   pip install lightstreamer-client-lib
#   from lightstreamer.client import LightstreamerClient, Subscription
#
# Constructor: LightstreamerClient(serverAddress, adapterSet='')
# Item names : raw numeric TT Instrument IDs prefixed with "TT-"
#              e.g.  "TT-14480190457373082110"
# ─────────────────────────────────────────────────────────────────────────────

SERVER_URL   = 'https://ls-md.corp.hertshtengroup.com/'
ADAPTER_SET  = 'TTsdkLSAdapter'  # CONFIRMED WORKING — error 71 resolved, live ticks received
DATA_ADAPTER = 'HGL1_Adapter'  # confirmed from colleague's working code

# ── CONTRACT MAPPING  (app_code → TT Instrument ID) ──────────────────────────
# • All IDs are the raw numeric string.
# • live_data.py subscribes as  "TT-" + tt_id
# • Leave blank ("") for any contract whose ID is not yet known.
# ─────────────────────────────────────────────────────────────────────────────
TT_MAPPING = {

    # ── SR1 Outrights (1-Month SOFR) ─────────────────────────────────────────
    "SR1J26": "12371713373671966825",    # SR1 Apr26
    "SR1K26": "8541084758762950878",     # SR1 May26
    "SR1M26": "17580263644204615428",    # SR1 Jun26
    "SR1N26": "3880399603150483481",     # SR1 Jul26
    "SR1Q26": "1431239809246394376",     # SR1 Aug26
    "SR1U26": "9309381137161962615",     # SR1 Sep26
    "SR1V26": "11434035541700322135",    # SR1 Oct26
    "SR1X26": "8373859479390367820",     # SR1 Nov26
    "SR1Z26": "638935919762336382",      # SR1 Dec26
    "SR1F27": "12267711630185759080",    # SR1 Jan27
    "SR1G27": "11818438006115878869",    # SR1 Feb27
    "SR1H27": "11368534221547994415",    # SR1 Mar27
    "SR1J27": "10267416492962537231",    # SR1 Apr27
    "SR1K27": "13003456520956211336",    # SR1 May27
    "SR1M27": "7274681043862095283",     # SR1 Jun27
    "SR1N27": "17587746350868461658",    # SR1 Jul27
    "SR1Q27": "15982701712321206525",    # SR1 Aug27
    "SR1U27": "4652571663407480418",     # SR1 Sep27

    # ── ZQ Outrights (30-Day Fed Funds) ──────────────────────────────────────
    "ZQJ26": "1820425921280870643",      # ZQ Apr26
    "ZQK26": "13509294969420576563",     # ZQ May26
    "ZQM26": "1173228227003061405",      # ZQ Jun26
    "ZQN26": "11804036294809825783",     # ZQ Jul26
    "ZQQ26": "8298997090319007208",      # ZQ Aug26
    "ZQU26": "7551864584289735302",      # ZQ Sep26
    "ZQV26": "7772853716872034867",      # ZQ Oct26
    "ZQX26": "13208077381270415860",     # ZQ Nov26
    "ZQZ26": "14618707670258439481",     # ZQ Dec26
    "ZQF27": "10173148798524565647",     # ZQ Jan27
    "ZQG27": "880647980586631019",       # ZQ Feb27
    "ZQH27": "887816061348387785",       # ZQ Mar27
    "ZQJ27": "410715719020149495",       # ZQ Apr27
    "ZQK27": "6196921965222780943",      # ZQ May27
    "ZQM27": "690279264195766323",       # ZQ Jun27
    "ZQN27": "2334564383434255324",      # ZQ Jul27
    "ZQQ27": "11729320422875922731",     # ZQ Aug27
    "ZQU27": "3324241383996491464",      # ZQ Sep27

    # ── SR3 Outrights (3-Month SOFR) — IDs from TT ───────────────────────────
    "SR3H26": "2264814074172926158",      # SR3 Mar26
    "SR3M26": "2518875037886751798",     # SR3 Jun26
    "SR3U26": "10056698436755136015",    # SR3 Sep26
    "SR3Z26": "3761391845186607269",     # SR3 Dec26
    "SR3H27": "8786029629332899618",     # SR3 Mar27
    "SR3M27": "6064266935547558467",     # SR3 Jun27
    "SR3U27": "10582686653072545408",    # SR3 Sep27
    "SR3Z27": "17925935412019565973",    # SR3 Dec27
    "SR3H28": "3822227243959035490",     # SR3 Mar28
    "SR3M28": "12741923103719175711",    # SR3 Jun28
    "SR3U28": "16673841811510079166",    # SR3 Sep28
    "SR3Z28": "7359239446017790966",     # SR3 Dec28
    "SR3H29": "4211986922965728750",     # SR3 Mar29
    "SR3M29": "11432813735419224277",    # SR3 Jun29
    "SR3U29": "9909662404632894188",     # SR3 Sep29
    "SR3Z29": "12350987571259131621",    # SR3 Dec29
    "SR3H30": "11906745505255579027",    # SR3 Mar30
    "SR3M30": "8236602463566917986",     # SR3 Jun30
    "SR3U30": "13762141828290349231",    # SR3 Sep30
    "SR3Z30": "5899392161601857848",     # SR3 Dec30

    # ── ZQ Calendar Spreads ───────────────────────────────────────────────────
    "ZQ_CAL_J26K26": "15582478317586972577",   # ZQ Apr26-May26 Calendar
    "ZQ_CAL_K26N26": "42727229478952816",      # ZQ May26-Jul26 Calendar
    "ZQ_CAL_N26Q26": "12082270800607194710",   # ZQ Jul26-Aug26 Calendar
    "ZQ_CAL_Q26V26": "7399630420570501092",    # ZQ Aug26-Oct26 Calendar
    "ZQ_CAL_V26X26": "10544706520320006277",   # ZQ Oct26-Nov26 Calendar
    "ZQ_CAL_X26F27": "8792228160823726282",    # ZQ Nov26-Jan27 Calendar
    "ZQ_CAL_F27G27": "12923396090304791527",   # ZQ Jan27-Feb27 Calendar
    "ZQ_CAL_G27J27": "16612610081924999085",   # ZQ Feb27-Apr27 Calendar
    "ZQ_CAL_J27K27": "3744068180779531100",    # ZQ Apr27-May27 Calendar
    "ZQ_CAL_K27N27": "4185657970561955484",    # ZQ May27-Jul27 Calendar
    "ZQ_CAL_N27Q27": "8238209401317660287",    # ZQ Jul27-Aug27 Calendar
    "ZQ_CAL_Q27U27": "4553286254424730619",    # ZQ Aug27-Sep27 Calendar
    "ZQ_CAL_V27X27": "1593101935173506965",    # ZQ Oct27-Nov27 Calendar

    # ── SR1/ZQ Inter-Product Spreads ──────────────────────────────────────────
    "SR1ZQ_J26": "6281703610889452058",
    "SR1ZQ_K26": "11041933593641959527",
    "SR1ZQ_M26": "5191397520103784040",
    "SR1ZQ_N26": "2519582500236661865",
    "SR1ZQ_Q26": "3787246620537445909",
    "SR1ZQ_U26": "4527157313805673452",
    "SR1ZQ_X26": "5119470236208447680",
    "SR1ZQ_Z26": "13078851335309038386",
    "SR1ZQ_F27": "7597510151731391400",
    "SR1ZQ_G27": "7402157535874790260",

    # ── ZQ Butterflies (meeting-adjacent) ────────────────────────────────────
    "ZQ_FLY_N26Q26V26": "9532262734862701783",   # ZQ Jul26 Aug26 Oct26 Butterfly
    "ZQ_FLY_Q26V26X26": "4328249578499890221",   # ZQ Aug26 Oct26 Nov26 Butterfly
    "ZQ_FLY_V26X26F27": "2183590315449818980",   # ZQ Oct26 Nov26 Jan27 Butterfly
    "ZQ_FLY_X26F27G27": "9245780982868988529",   # ZQ Nov26 Jan27 Feb27 Butterfly
    "ZQ_FLY_F27G27J27": "12538070783725349035",  # ZQ Jan27 Feb27 Apr27 Butterfly
    "ZQ_FLY_G27J27K27": "4528330393275859885",   # ZQ Feb27 Apr27 May27 Butterfly
    "ZQ_FLY_J27K27N27": "6855486555730353592",   # ZQ Apr27 May27 Jul27 Butterfly

    # ── SR3 Calendar Spreads (1Q) ────────────────────────────────────────────
    "SR3_CAL_H26M26": "564618620093690082",       # SR3 Mar26-Jun26 Calendar
    "SR3_CAL_M26U26": "10613911634636906096",     # SR3 Jun26-Sep26 Calendar
    "SR3_CAL_U26Z26": "10538177603741347940",     # SR3 Sep26-Dec26 Calendar
    "SR3_CAL_Z26H27": "15292306285496321895",     # SR3 Dec26-Mar27 Calendar
    "SR3_CAL_H27M27": "9440282357390122061",      # SR3 Mar27-Jun27 Calendar
    "SR3_CAL_M27U27": "1074193527039132483",      # SR3 Jun27-Sep27 Calendar
    "SR3_CAL_U27Z27": "5027144285602730053",      # SR3 Sep27-Dec27 Calendar
    "SR3_CAL_Z27H28": "5004080736027242281",      # SR3 Dec27-Mar28 Calendar
    "SR3_CAL_H28M28": "15781040958777106512",     # SR3 Mar28-Jun28 Calendar
    "SR3_CAL_M28U28": "3590265153926145762",      # SR3 Jun28-Sep28 Calendar
    "SR3_CAL_U28Z28": "6016657214449980661",      # SR3 Sep28-Dec28 Calendar
    "SR3_CAL_Z28H29": "14572902716380660001",     # SR3 Dec28-Mar29 Calendar
    "SR3_CAL_H29M29": "10503523860245957343",     # SR3 Mar29-Jun29 Calendar
    "SR3_CAL_M29U29": "15887690782750499864",     # SR3 Jun29-Sep29 Calendar
    "SR3_CAL_U29Z29": "4551460361751458361",      # SR3 Sep29-Dec29 Calendar
    "SR3_CAL_Z29H30": "11690798471030593898",     # SR3 Dec29-Mar30 Calendar
    "SR3_CAL_H30M30": "12984309245533959438",     # SR3 Mar30-Jun30 Calendar
    "SR3_CAL_M30U30": "1702078066897695795",      # SR3 Jun30-Sep30 Calendar
    "SR3_CAL_U30Z30": "6051097766110792341",      # SR3 Sep30-Dec30 Calendar
}

# ── Inverse mapping: TT ID → app_code (auto-generated, do NOT edit) ───────────
INV_TT_MAPPING = {v: k for k, v in TT_MAPPING.items() if v}

# ── Fields to request from HGL1_Adapter ──────────────────────────────────────
# Matches the confirmed working field list from colleague's code.
FIELD_NAMES = [
    'command',
    'Exchange', 'Contract', 'Product', 'InstrumentId',
    'ClientRecvTime', 'ExchangeRecvTime', 'ServerRecvTime',
    'Open', 'High', 'Low', 'Close', 'Volume',
    'Last', 'LastQty',
    'SeriesStatus',
    'Settle', 'PrevSettle',
    'BestAsk', 'BestAskQty',
    'BestBid', 'BestBidQty',
    'IndSettle', 'Price', 'AdminPrice', 'Admin', 'Direction',
    'VWAP',
]
