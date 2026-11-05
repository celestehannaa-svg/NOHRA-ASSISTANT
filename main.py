def get_week_from_date(date_str):
    """Tue - Sun week: e.g., 28 Oct (Tue) -> 28 Oct - 2 Nov"""
    try:
        dt = datetime.strptime(date_str + " 2025", "%d %b %Y")
        weekday = dt.weekday()  # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
        if weekday == 0:  # Monday off - belongs to next Tue-Sun week
            tuesday = dt + timedelta(days=1)
        else:
            tuesday = dt - timedelta(days=(weekday - 1))
        sunday = tuesday + timedelta(days=5)  # Tue +5 = Sun
        if tuesday.month == sunday.month:
            return f"{tuesday.day} - {sunday.day} {tuesday.strftime('%b')}"
        else:
            return f"{tuesday.day} {tuesday.strftime('%b')} - {sunday.day} {sunday.strftime('%b')}"
    except:
        return "28 Oct - 2 Nov"
