(let [now       (java.time.LocalDateTime/now)
      fmt       (java.time.format.DateTimeFormatter/ofPattern "yyyy-MM-dd HH:mm:ss")
      timestamp (.format now fmt)
      header    (str "─── Session started " timestamp " ───\n")
      path      (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")]
  (spit path header :append true))
