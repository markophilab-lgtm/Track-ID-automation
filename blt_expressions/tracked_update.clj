(let [n      (.getTrackNumber status)
      last-n (get @locals :t -1)]
  ;; New track: reset logged flag
  (when (and (pos? n) (not= n last-n))
    (swap! locals assoc :t n :logged false))
  ;; Write the first moment metadata is available for an unlogged track
  (when (and (pos? n) track-metadata (not (get @locals :logged false)))
    (swap! locals assoc :logged true)
    (let [art      (.getArtist track-metadata)
          artist   (if art (.label art) "Unknown Artist")
          title    (or (.getTitle track-metadata) "Unknown Title")
          time-str (.format (java.time.LocalDateTime/now)
                            (java.time.format.DateTimeFormatter/ofPattern "HH:mm:ss"))]
      (spit (str (System/getProperty "user.home") "/Desktop/tracklist_live.txt")
            (str time-str "  [Player " (.getDeviceNumber status) "]  "
                 artist " — " title "\n")
            :append true))))
