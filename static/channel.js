function findOffset(element) {
    var top = 0, left = 0;

    do {
        top += element.offsetTop  || 0;
        left += element.offsetLeft || 0;
        element = element.offsetParent;
    } while(element);

    return {
        top: top,
        left: left
    };
}

window.onload = function () {
    var maincontent = document.getElementById("maincontent");
    var titlebar = document.getElementById("maintitlebar");
    var stickyHeader = document.getElementById("channelmenu");
    var headerOffset = findOffset(stickyHeader).top - titlebar.offsetHeight;

    maincontent.onscroll = function() {
        var bodyScrollTop = maincontent.scrollTop;
        if (bodyScrollTop > headerOffset) {
            stickyHeader.classList.add("sticky");
        } else {
            stickyHeader.classList.remove("sticky");
        }
    };
};
