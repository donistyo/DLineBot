class SmartScalpingView:

    @staticmethod
    def show(data):
        if not data:
            return

        print()
        print("=" * 60)
        print("SMART SCALPING ENGINE")
        print("=" * 60)

        ss = data.get("scalp_score", {})
        grade = ss.get("grade", "-")
        score = ss.get("score", 0)
        direction = ss.get("direction", "NEUTRAL")
        print(f"SCALP SCORE  {score:.0f}/100  {grade}  [{direction}]")
        print()

        engines_emoji = {
            "momentum": "⚡",
            "speed": "�",
            "liquidity": "💧",
            "fake_breakout": "🎯",
            "session": "🌍",
            "impulse": "💥",
        }

        for key, emoji in engines_emoji.items():
            eng = data.get(key, {})
            if not eng:
                continue
            score = eng.get("score", 0)
            label = key.replace("_", " ").title()
            if key == "momentum":
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('direction','-')}]  body:{eng.get('body_ratio',0):.1f}x  accel:{eng.get('acceleration',0):.2f}")
            elif key == "speed":
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('level','-')}]  {eng.get('speed',0):.2f}/candle")
            elif key == "liquidity":
                stop = "⚠️ STOP HUNT" if eng.get("stop_hunt") else ""
                grab = "💰 LIQ GRAB" if eng.get("liquidity_grab") else ""
                extra = f"  {stop} {grab}".strip()
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('signal','-')}]{extra}")
            elif key == "fake_breakout":
                fake = "⚠️ FAKE" if eng.get("fake_breakout") else ""
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('signal','-')}]  {fake}")
            elif key == "session":
                overlap = "🔀 OVERLAP" if eng.get("is_overlap") else ""
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('session','-')}]  {overlap}")
            elif key == "impulse":
                imp = "💥 IMPULSE" if eng.get("impulse") else ""
                print(f"  {emoji} {label:20s} {score:3d}  [{eng.get('signal','-')}]  {imp}")

        print()
        details = ss.get("details", {})
        if details:
            parts = [f"{k.replace('_',' ').title()} {v}" for k, v in sorted(details.items(), key=lambda x: -x[1])]
            print(f"  Details: {' | '.join(parts)}")
        print()
        print(f"  Action: {ss.get('action', 'WAIT')}")
