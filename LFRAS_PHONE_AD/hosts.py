from django_hosts import patterns, host

host_patterns = patterns(
    "lfras_phone_ad.hosts",  # just a namespace label; not a module
    host(r"site", "marketing.urls", name="site"),  # site.lucidcompliances.com
    host(r"lfras", "lfras_phone_ad.urls", name="app"),  # lfras.lucidcompliances.com
)
