# import this file into RouterOS, then create /system scheduler on rf-update-all
/system script
add name="rf-update-all" policy=read,write,test source={
    :local baseUrl "https://raw.githubusercontent.com/sip-it/build_rsc/release"
    :local files {"rsc/geoip/ru-blocked.rsc";"rsc/geoip/ru-blocked-community.rsc";"rsc/geoip/re-filter.rsc";"rsc/geoip/cloudflare.rsc";"rsc/geoip/google.rsc";"rsc/geoip/ddos-guard.rsc";"rsc/geosite/ru-blocked.rsc";"rsc/geosite/google.rsc";"rsc/geosite/youtube.rsc";"rsc/geosite/discord.rsc";"rsc/geosite/category-ads-all.rsc";"rsc/geosite/win-spy.rsc";"rsc/geosite/win-update.rsc";"rsc/geosite/win-extra.rsc"}

    :foreach f in=$files do={
        :local url ($baseUrl . "/" . $f)
        :local dst ("tmp-" . [:pick $f ([:find $f "/" -1] + 1) [:len $f]])

        :log info ("rf-update-all: fetching " . $url)
        :do {
            /tool fetch url=$url dst-path=$dst keep-result=yes
            /import file-name=$dst verbose=yes
            /file remove [find where name=$dst]
        } on-error={
            :log error ("rf-update-all: failed " . $url)
            :if ([:len [/file find where name=$dst]] > 0) do={
                /file remove [find where name=$dst]
            }
        }
    }
}
