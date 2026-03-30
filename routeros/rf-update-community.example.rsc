/system script
add name=rf-update-community policy=read,write,test source={
    :local url "https://raw.githubusercontent.com/sip-it/build_rsc/release/rsc/community-antifilter.rsc"
    :local dst "tmp-community-antifilter.rsc"
    :local listName "antifilter-community"
    :log info ("rf-update-community: downloading " . $url)
    :do {
        /tool fetch url=$url dst-path=$dst keep-result=yes
        :if ([:len [/file find where name=$dst]] = 0) do={
            :error "downloaded file not found after fetch"
        }
        :log info ("rf-update-community: cleaning static entries in list " . $listName)
        /ip firewall address-list remove [/ip firewall address-list find where list=$listName and dynamic=no]
        :delay 3s
        :onerror e in={
            /import file-name=$dst verbose=yes
        } do={
            :log error ("rf-update-community: import failed: " . $e)
            :error $e
        }
        :log info "rf-update-community: import done"
    } on-error={
        :log error ("rf-update-community: failed: " . $message)
    }
    :if ([:len [/file find where name=$dst]] > 0) do={
        /file remove [find where name=$dst]
    }
}
