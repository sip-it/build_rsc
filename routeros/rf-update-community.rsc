# Example update script for RouterOS
/system script
add name=rf-update-community policy=read,write,test source={
    :local baseUrl "https://raw.githubusercontent.com/sip-it/build_rsc/release"
    :local file "rsc/community-antifilter.rsc"
    :local url ($baseUrl . "/" . $file)
    :local dst "tmp-community-antifilter.rsc"
    :log info ("rf-update-community: downloading " . $url)
    :do {
        /tool fetch url=$url dst-path=$dst keep-result=yes
        :if ([:len [/file find where name=$dst]] = 0) do={
            :error ("download failed: " . $file)
        }
        /import file-name=$dst verbose=yes
        /file remove [find where name=$dst]
        :log info ("rf-update-community: imported " . $file)
    } on-error={
        :log error ("rf-update-community: failed " . $file)
        :if ([:len [/file find where name=$dst]] > 0) do={
            /file remove [find where name=$dst]
        }
    }
}
