# Example update script for RouterOS
/system script
add name=rf-update-all policy=read,write,test source={
    :local baseUrl "https://raw.githubusercontent.com/<OWNER>/<REPO>/release"
    :local files {
        "rsc/geoip/re-filter.rsc";
        "rsc/geoip/cloudflare.rsc";
        "rsc/geoip/google.rsc";
        "rsc/geoip/ddos-guard.rsc";
        "rsc/geosite/refilter.rsc";
        "rsc/geosite/google.rsc";
        "rsc/geosite/youtube.rsc";
        "rsc/geosite/discord.rsc";
        "rsc/geosite/category-ads-all.rsc";
        "rsc/geosite/win-spy.rsc";
        "rsc/geosite/win-update.rsc";
        "rsc/geosite/win-extra.rsc";
    }
    :foreach f in=$files do={
        :local url ($baseUrl . "/" . $f)
        :local dst ("tmp-" . [:pick $f ([:find $f "/" -1] + 1) [:len $f]])
        :log info ("rf-update-all: downloading " . $url)
        :do {
            /tool fetch url=$url dst-path=$dst keep-result=yes
            :if ([:len [/file find where name=$dst]] = 0) do={
                :error ("download failed: " . $f)
            }
            /import file-name=$dst verbose=yes
            /file remove [find where name=$dst]
            :log info ("rf-update-all: imported " . $f)
        } on-error={
            :log error ("rf-update-all: failed " . $f)
            :if ([:len [/file find where name=$dst]] > 0) do={
                /file remove [find where name=$dst]
            }
        }
    }
}
