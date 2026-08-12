# Локальные PNG-визуализации

`make reproduce` создаёт шесть PNG: weekly trends, zone-hour heatmap, availability/conversion curve, weekday/weekend comparison, seasonality и компактный static dashboard.

Файлы намеренно исключены из Git: одинаковые data и код могут давать разные байты из-за версии freetype, системных шрифтов и PNG-метаданных. Для портфельного просмотра используйте версионируемый [self-contained dashboard](../../artifacts/fleet_dashboard.html) и [report](../../artifacts/analysis_report.html); их входные JSON snapshot регенерируются и проверяются в CI.
