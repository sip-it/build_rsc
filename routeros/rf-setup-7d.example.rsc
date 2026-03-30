# Import update scripts from release first:
# rf-update-community.example.rsc
# rf-update-dns-adlist.example.rsc
:local dnsUrl "https://raw.githubusercontent.com/sip-it/build_rsc/release/dns/category-ads-all.txt"
/ip dns adlist
:if ([:len [find where url=$dnsUrl]] = 0) do={ add url=$dnsUrl ssl-verify=no }
/system scheduler remove [find where name="rf-update-community-7d"]
/system scheduler add name="rf-update-community-7d" start-time=03:10:00 interval=7d on-event=rf-update-community
/system scheduler remove [find where name="rf-update-dns-adlist-7d"]
/system scheduler add name="rf-update-dns-adlist-7d" start-time=03:20:00 interval=7d on-event=rf-update-dns-adlist
