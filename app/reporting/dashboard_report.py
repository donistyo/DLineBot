from pathlib import Path


class DashboardReport:

    def __init__(self):

        self.output_dir = Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        report,
        performance,
        symbol,
        timeframe
    ):

        html = f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<title>DLineBot Report</title>

<style>

body{{
font-family:Arial;
margin:40px;
background:#fafafa;
}}

h1,h2{{
color:#1f2937;
}}

table{{
border-collapse:collapse;
width:450px;
}}

td,th{{
border:1px solid #ddd;
padding:8px;
}}

img{{
width:900px;
margin-top:20px;
margin-bottom:30px;
border:1px solid #ddd;
}}

</style>

</head>

<body>

<h1>DLineBot Enterprise Report</h1>

<h2>General Information</h2>

<table>

<tr><td>Symbol</td><td>{symbol}</td></tr>
<tr><td>Timeframe</td><td>{timeframe}</td></tr>
<tr><td>Total Trade</td><td>{report['total_trade']}</td></tr>

</table>

<h2>Performance</h2>

<table>

<tr><td>Initial Balance</td><td>${performance['initial_balance']:.2f}</td></tr>

<tr><td>Ending Balance</td><td>${performance['ending_balance']:.2f}</td></tr>

<tr><td>Net Profit</td><td>${performance['net_profit']:.2f}</td></tr>

<tr><td>ROI</td><td>{performance['roi']:.2f}%</td></tr>

<tr><td>Win Rate</td><td>{report['win_rate']:.2f}%</td></tr>

<tr><td>Profit Factor</td><td>{performance['profit_factor']:.2f}</td></tr>

<tr><td>Max Drawdown</td><td>{performance['max_drawdown']:.2f}%</td></tr>

</table>

<h2>Equity Curve</h2>

<img src="equity_curve.png">

<h2>Drawdown Curve</h2>

<img src="drawdown_curve.png">

<h2>Signal Distribution</h2>

<img src="signal_distribution.png">

<h2>Feature Importance</h2>

<img src="feature_importance.png">

</body>

</html>
"""

        output = self.output_dir / "dashboard_report.html"

        output.write_text(
            html,
            encoding="utf-8"
        )

        return str(output)