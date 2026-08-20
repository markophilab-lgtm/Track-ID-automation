;; Tracked Update Expression — tracklist logging + key-to-light.
;;
;; Replaces tracked_update.clj. The logging half is unchanged and runs FIRST,
;; so a light failure can never cost us a tracklist line. The light half only
;; acts for the tempo master, and hands the actual work to
;; `python3 -m keylight.cli` in a future, so BLT's update thread never blocks.
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
            :append true)))

  ;; ---- key-to-light -------------------------------------------------------
  (try
    (let [key-item (when track-metadata (.getKey track-metadata))
          key-str  (when key-item (.label key-item))
          now-ms   (System/currentTimeMillis)
          last-key (get @locals :light-key)
          last-at  (get @locals :light-at 0)]
      ;; Room follows the tempo master only. No key tag: hold the current color.
      ;; Same key as the room already shows: nothing to do.
      ;; Debounce 2s so a master handoff mid-blend doesn't strobe the room.
      (when (and (.isTempoMaster status)
                 (.isPlaying status)
                 key-str
                 (not= key-str last-key)
                 (> (- now-ms last-at) 2000))
        (swap! locals assoc :light-key key-str :light-at now-ms)
        (future
          (try
            (let [repo (str (System/getProperty "user.home") "/git/track_id_project")
                  pb   (java.lang.ProcessBuilder.
                        (into-array String
                                    ["python3" "-m" "keylight.cli" "--quiet" key-str]))]
              (.directory pb (java.io.File. repo))
              (.redirectErrorStream pb true)
              (let [proc (.start pb)]
                (.waitFor proc 5 java.util.concurrent.TimeUnit/SECONDS)))
            (catch Throwable t
              (timbre/warn t "keylight: could not run color update"))))))
    (catch Throwable t
      ;; Lights are decoration; logging is the job. Never rethrow.
      (timbre/warn t "keylight: skipped color update"))))
