$(document).ready(function() {
    try {
        let re = new RegExp($("#text_input").val(), 'gim')
        $(".text_output").markRegExp(re, {
            "acrossElements": true
        });
    } catch (error) {
        //console.error(error)
    }

    var last_seconds = 0

    $(".seconds").click(function(event) {
        var seconds = $(this).attr("seconds")
        $(this).closest("tr").find(".audio_player").currentTime = seconds
        console.log("seconds " + seconds)
        var audio_player = $(this).closest("tr").find(".audio_player")[0]

        last_seconds = seconds
        console.log("last_seconds " + last_seconds)

        // if the same seconds, pause or play


        if (audio_player.paused) {
            // if not the last player
            audio_player.currentTime = seconds
            audio_player.play()
        } else {
            audio_player.pause()
        }



    });

    $(".playback_rate").change(function(event) {
        $(".playback_rate").val(this.value)
        var players = $(".audio_player")

        for (let i = 0; i < players.length; i++) {
            players[i].playbackRate = this.value
        }

        if (this.value != 1) { $(".playback_rate_label").text("Rate=" + this.value) }
    });

    $(".playback_rate_reset").click(function(event) {
        $(".playback_rate").val(1)
        var players = $(".audio_player")

        for (let i = 0; i < players.length; i++) {
            players[i].playbackRate = 1
        }

        $(".playback_rate_label").text("Rate")
    });
});