//+------------------------------------------------------------------+
//| DLineExecutor: eksekutor saja. Keputusan ada di bot Python.      |
//| Baca Common\Files\dline\cmd\*.req (key=value), tulis ack\*.ack.  |
//+------------------------------------------------------------------+
#property strict

input string InpDir          = "dline";
input int    InpPollMs       = 200;
input int    InpTtlSec       = 5;      // tolak perintah lebih tua dari ini
input string InpMagics       = "10001,10002,10003";
input double InpMaxLot       = 0.05;
input int    InpMaxPositions = 8;
input int    InpMaxSpreadPts = 0;      // 0 = mati; hanya berlaku untuk order baru

string g_done[200];
int    g_doneN = 0;

int OnInit()
{
   bool ok = EventSetMillisecondTimer(InpPollMs);
   Print("DLineExecutor init, timer=", ok, " dir=", InpDir, " common=", TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); }

string Val(string &k[], string &v[], string key)
{
   for(int i = 0; i < ArraySize(k); i++) if(k[i] == key) return v[i];
   return "";
}

bool MagicAllowed(long magic)
{
   string p[];
   int n = StringSplit(InpMagics, ',', p);
   for(int i = 0; i < n; i++) if((long)StringToInteger(p[i]) == magic) return true;
   return false;
}

int OwnPositions()
{
   int c = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t > 0 && MagicAllowed(PositionGetInteger(POSITION_MAGIC))) c++;
   }
   return c;
}

bool Seen(string id)
{
   for(int i = 0; i < g_doneN; i++) if(g_done[i] == id) return true;
   return false;
}

void Remember(string id)
{
   if(g_doneN == ArraySize(g_done)) { for(int i = 1; i < g_doneN; i++) g_done[i-1] = g_done[i]; g_doneN--; }
   g_done[g_doneN++] = id;
}

void Ack(string id, uint retcode, string comment, ulong order, ulong deal, double vol, double price)
{
   string tmp = InpDir + "\\ack\\" + id + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE) { Print("DLineExecutor: gagal tulis ack, err=", GetLastError()); return; }
   FileWriteString(h, "retcode=" + (string)retcode + "\n");
   FileWriteString(h, "comment=" + comment + "\n");
   FileWriteString(h, "order=" + (string)order + "\n");
   FileWriteString(h, "deal=" + (string)deal + "\n");
   FileWriteString(h, "volume=" + DoubleToString(vol, 2) + "\n");
   FileWriteString(h, "price=" + DoubleToString(price, 8) + "\n");
   FileClose(h);
   if(!FileMove(tmp, FILE_COMMON, InpDir + "\\ack\\" + id + ".ack", FILE_COMMON | FILE_REWRITE)) Print("DLineExecutor: gagal pindah ack, err=", GetLastError());
}

void Handle(string file)
{
   // klaim atomik: hanya satu instance EA yang berhasil me-rename, yang lain mundur
   string src = InpDir + "\\cmd\\" + file;
   string run = src + ".run";
   if(!FileMove(src, FILE_COMMON, run, FILE_COMMON)) return;
   Print("DLineExecutor: menemukan ", file);
   int h = FileOpen(run, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
   if(h == INVALID_HANDLE) { Print("DLineExecutor: gagal buka, err=", GetLastError()); return; }
   string k[], v[];
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      int e = StringFind(line, "=");
      if(e < 1) continue;
      int n = ArraySize(k);
      ArrayResize(k, n + 1); ArrayResize(v, n + 1);
      k[n] = StringSubstr(line, 0, e);
      v[n] = StringSubstr(line, e + 1);
   }
   FileClose(h);
   if(!FileDelete(run, FILE_COMMON)) Print("DLineExecutor: gagal hapus cmd, err=", GetLastError());

   string id = Val(k, v, "id");
   if(id == "") return;
   if(Seen(id)) return;                                  // anti-duplikat
   Remember(id);

   if(TimeGMT() - (datetime)StringToInteger(Val(k, v, "ts")) > InpTtlSec)
   { Ack(id, 10031, "EA: perintah kedaluwarsa", 0, 0, 0, 0); return; }

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = (ENUM_TRADE_REQUEST_ACTIONS)StringToInteger(Val(k, v, "action"));
   req.symbol       = Val(k, v, "symbol");
   req.volume       = StringToDouble(Val(k, v, "volume"));
   req.type         = (ENUM_ORDER_TYPE)StringToInteger(Val(k, v, "type"));
   req.price        = StringToDouble(Val(k, v, "price"));
   req.sl           = StringToDouble(Val(k, v, "sl"));
   req.tp           = StringToDouble(Val(k, v, "tp"));
   req.stoplimit    = StringToDouble(Val(k, v, "stoplimit"));
   req.deviation    = (ulong)StringToInteger(Val(k, v, "deviation"));
   req.magic        = (ulong)StringToInteger(Val(k, v, "magic"));
   req.position     = (ulong)StringToInteger(Val(k, v, "position"));
   req.order        = (ulong)StringToInteger(Val(k, v, "order"));
   req.comment      = Val(k, v, "comment");
   req.type_time    = (ENUM_ORDER_TYPE_TIME)StringToInteger(Val(k, v, "type_time"));
   req.type_filling = (ENUM_ORDER_TYPE_FILLING)StringToInteger(Val(k, v, "type_filling"));

   bool isNew = (req.action == TRADE_ACTION_PENDING) || (req.action == TRADE_ACTION_DEAL && req.position == 0);

   // pagar: hanya magic milik bot
   long magic = (long)req.magic;
   if(req.position > 0 && PositionSelectByTicket(req.position)) magic = PositionGetInteger(POSITION_MAGIC);
   if(req.action == TRADE_ACTION_REMOVE && OrderSelect(req.order)) magic = OrderGetInteger(ORDER_MAGIC);
   if(!MagicAllowed(magic)) { Ack(id, 10013, "EA: magic tidak diizinkan", 0, 0, 0, 0); return; }

   if(isNew)
   {
      if(req.volume <= 0 || req.volume > InpMaxLot)
      { Ack(id, 10014, "EA: lot melebihi batas", 0, 0, 0, 0); return; }
      if(OwnPositions() >= InpMaxPositions)
      { Ack(id, 10033, "EA: batas posisi", 0, 0, 0, 0); return; }
      if(InpMaxSpreadPts > 0 && SymbolInfoInteger(req.symbol, SYMBOL_SPREAD) > InpMaxSpreadPts)
      { Ack(id, 10021, "EA: spread terlalu lebar", 0, 0, 0, 0); return; }
   }

   if(!OrderSend(req, res) && res.retcode == 0) res.retcode = 10018; // gagal kirim, tanpa jawaban server
   Print("DLineExecutor: id=", id, " retcode=", res.retcode);
   Ack(id, res.retcode, res.comment, res.order, res.deal, res.volume, res.price);
}

void OnTimer()
{
   string name;
   // MQL5 menolak ekstensi .cmd (err 5002), makanya .req; "*.*" lalu disaring .req di bawah
   long fh = FileFindFirst(InpDir + "\\cmd\\*.*", name, FILE_COMMON);
   if(fh == INVALID_HANDLE) return;
   string files[];
   do { if(StringLen(name) > 4 && StringSubstr(name, StringLen(name) - 4) == ".req") { int n = ArraySize(files); ArrayResize(files, n + 1); files[n] = name; } }
   while(FileFindNext(fh, name));
   FileFindClose(fh);
   for(int i = 0; i < ArraySize(files); i++) Handle(files[i]);
}
