import json
import os
import time

from app.config.settings import get_trade_config


BASKET_STATUS_PATH = "runtime/basket_status.json"

# Cluster: tiket bot dengan selisih waktu <= 45 detik dianggap
# satu batch entry (spacing entry searah minimum 60 detik,
# jadi batch berbeda tidak pernah menyatu).
BATCH_WINDOW_SECONDS = 45.0


def _epoch(t):
    """Samakan time.time() dengan position.time (datetime ATAU epoch)."""
    if hasattr(t, "timestamp"):
        return float(t.timestamp())
    return float(t)


class BasketGuard:
    """Tutup seluruh layer premium (basket) sekaligus.

    Kebijakan (terkonfirmasi user, 28 Sep):
      - Cut: floating basket <= basket_cut_usd (default -10 USD),
        skala proporsional terhadap sisa layer
        (7 layer sudah TP -> sisa 3 boleh turun -3, bukan -10).
      - Timeout: umur basket >= basket_timeout_min (default 15 menit)
        -> tutup sisa layer, berapa pun floatingnya.
      - Hanya batch >= layer_count/2 tiket (default 5) yang dijaga;
        fallback dual (2 layer) tetap pakai SL per-layer seperti biasa.
      - Close memakai caller BASKET_CUT / BASKET_TIME -> masuk hitungan
        sl_events di HistoryManager -> istirahat SL-break tetap aktif.
    """

    def __init__(self):
        self._n_initial = {}

    def _cfg(self):
        try:
            layer_count = int(get_trade_config("layer_count", 10) or 0)
        except Exception:
            layer_count = 10
        if layer_count < 2:
            layer_count = 2
        try:
            cut = float(get_trade_config("basket_cut_usd", -10))
        except Exception:
            cut = -10.0
        try:
            timeout_min = float(get_trade_config("basket_timeout_min", 15))
        except Exception:
            timeout_min = 15.0
        return {
            "min_size": max(2, layer_count // 2),
            "cut": cut,
            "timeout_s": max(1.0, timeout_min * 60.0),
            "timeout_min": timeout_min,
        }

    @staticmethod
    def _is_bot(position):
        comment = getattr(position, "comment", "") or ""
        return comment.startswith("DLineBot")

    @staticmethod
    def _clusters(positions):
        """Kelompokkan per arah + jendela waktu 45 detik."""
        groups = []
        for p in sorted(positions, key=lambda x: _epoch(x.time)):
            if (groups
                    and p.type == groups[-1][0].type
                    and _epoch(p.time) - _epoch(groups[-1][0].time) <= BATCH_WINDOW_SECONDS):
                groups[-1].append(p)
            else:
                groups.append([p])
        return groups

    def process(self, positions, symbol=None, controller=None):
        results = []
        cfg = self._cfg()
        seen_keys = set()
        status_batches = []

        bot_positions = [p for p in positions if self._is_bot(p)]

        for group in self._clusters(bot_positions):
            n = len(group)

            first_time = _epoch(group[0].time)
            key = (int(group[0].type), int(first_time))

            # Batch premium dinilai dari jumlah AWAL (n_initial),
            # bukan sisa sekarang: 7 layer sudah TP -> sisa 3 tetap
            # dijaga cut proporsional. Batch yang bukan premium
            # (fallback dual dsb) tidak pernah disimpan di memori.
            n0 = self._n_initial.get(key)
            if n0 is None:
                n0 = n
            if n0 < cfg["min_size"]:
                continue
            seen_keys.add(key)
            n0 = max(int(n0), n)
            self._n_initial[key] = n0

            total = sum(float(p.profit) for p in group)
            age = max(0.0, time.time() - first_time)
            cut_effective = cfg["cut"] * (n / n0)

            hit_cut = total <= cut_effective
            hit_timeout = age >= cfg["timeout_s"]

            status_batches.append({
                "direction": "BUY" if int(group[0].type) == 0 else "SELL",
                "tickets": n,
                "n_initial": n0,
                "floating": round(total, 2),
                "cut_effective": round(cut_effective, 2),
                "age_min": round(age / 60.0, 1),
            })

            if not (hit_cut or hit_timeout):
                continue

            caller = "BASKET_CUT" if hit_cut else "BASKET_TIME"
            if hit_cut:
                reason = (f"Basket {total:.2f} <= cut {cut_effective:.2f} "
                          f"({n}/{n0} layer tersisa) - tutup semua layer.")
            else:
                reason = (f"Umur basket {age / 60.0:.1f} menit >= "
                          f"{cfg['timeout_min']:.0f} menit "
                          f"({n}/{n0} layer tersisa) - tutup semua layer.")

            for p in group:
                res = None
                if controller is not None:
                    res = controller.close(p, caller=caller)
                results.append({
                    "status": "CLOSED",
                    "action": caller,
                    "reason": reason,
                    "ticket": p.ticket,
                    "result": res,
                })

        # Lupakan batch yang sudah tidak ada
        for k in list(self._n_initial.keys()):
            if k not in seen_keys:
                del self._n_initial[k]

        try:
            os.makedirs("runtime", exist_ok=True)
            with open(BASKET_STATUS_PATH, "w") as f:
                json.dump({
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "active": status_batches,
                }, f, indent=2)
        except Exception:
            pass

        return results
