import re

_times = dict(d=86400.0, h=3600.0, m=60.0, s=1.0, ms=0.001)
_r = (
    r"^"
    r"(?=.*[dhms(ms)]$)"
    r"((?P<d>\d+)(?:d\s*))?"
    r"((?P<h>\d+)(?:h\s*))?"
    r"((?P<m>\d+)(?:m\s*))?"
    r"((?P<s>\d+)(?:s\s*))?"
    r"((?P<ms>\d+)(?:ms\s*))?"
    r"$"
)


def interval_to_second(interval: str) -> float:
    """1s12h35m59s500msのような文字列を秒数に変換する

    Args:
        interval (str): 時間を表す文字列

    Raises:
        ValueError: 変換できなかったときの例外

    Returns:
        float: 秒数
    """
    m = re.match(_r, interval)

    if m is None:
        raise ValueError(f'intervalは[1d12h35m59s500ms]のような形である必要があります。入力: "{interval}"')

    return sum([_times[k] * int(v) for k, v in m.groupdict().items() if v is not None])
