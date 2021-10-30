$(document).ready(function() {
    try {
        let re = new RegExp($("#text_input").val(), 'gim')
        $(".text_output").markRegExp(re);
    } catch (error) {
        //console.error(error)
    }

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