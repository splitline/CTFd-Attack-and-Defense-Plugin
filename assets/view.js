CTFd._internal.challenge.data = undefined

CTFd._internal.challenge.renderer = CTFd.lib.markdown();


CTFd._internal.challenge.preRender = function () { }

CTFd._internal.challenge.render = function (markdown) {
    return CTFd._internal.challenge.renderer.render(markdown)
}

CTFd._internal.challenge.postRender = function () {
    document.querySelector('.challenge-scoreboard').addEventListener('click', function (e) {
        fetch('/plugins/awd/api/scoreboard/' + CTFd._internal.challenge.data.name)
            .then(function (response) {
                return response.json()
            }
            ).then(function (data) {
                document.getElementById('challenge-scoreboard-body').innerHTML =
                    data.map((d, i) => `<tr>
                    <td>${i+1}</td>
                    <td><a href="/teams/${d[0]}">${d[1]}</a></td>
                    <td>${+d[2]} / ${+d[3]}</td>
                    <td>${+d[4]}</td></tr>`).join('')
            });
    });
}

