<!-- 지도 상호작용 JS (Day 8 확정 UX 자산 — ui/map_view.py가 string.Template로 주입)

     Template 치환자: $min_r, $max_r (반경 한계, m)

     동작 요약:
     - 원 영역 아무 곳이나 잡고 드래그해서 분석 중심을 옮긴다. 끄는 동안 원+핀이 커서를
       따라오고, 놓는 순간 원 중심 좌표로 지도 click 이벤트를 합성해 쏜다 —
       streamlit-folium은 도형 드래그를 파이썬으로 돌려주지 않지만 지도 click은
       last_clicked로 돌려주므로 ui/channels.py의 처리 로직이 그대로 받는다.
     - 원 가장자리(±12px 밴드)를 잡으면 반경 조절 모드 — 놓으면 50m 스텝으로 스냅하고,
       새 반경을 핀 툴팁에 "TURF_RADIUS:값:논스"로 심은 뒤 핀 click을 합성해
       last_object_clicked_tooltip 채널로 전달한다.
     - 드래그 직후 브라우저가 만드는 잔여 click(원 위에서 mouseup)은 캡처 단계에서 한 번
       삼켜 last_clicked를 덮어쓰지 못하게 한 뒤 합성 click을 보낸다.
     - Leaflet 1.9는 지도 팬을 pointerdown에서 시작하므로(Browser.touch=true) 반드시
       pointerdown을 path 요소에서 직접 잡아 전파를 차단해야 지도가 대신 끌리지 않는다.
     - folium.Element는 지도 JS 초기화보다 먼저 렌더되므로 img onload + 재시도 패턴으로
       늦게 실행한다. streamlit-folium은 지도의 Leaflet 변수명을 map_div로 고정한다. -->
<img src="data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="
     style="display:none" onload="
    (function() {
        function turfInitDrag() {
            if (typeof map_div === 'undefined') { setTimeout(turfInitDrag, 50); return; }
            var pin = null, circle = null;
            map_div.eachLayer(function(l) {
                if (l instanceof L.Marker && l.options.draggable) { pin = l; }
                if (l instanceof L.Circle && l.getRadius && l.getRadius() >= 50) { circle = l; }
            });
            if (!pin || !circle || !circle.getElement()) { setTimeout(turfInitDrag, 50); return; }

            function commit() {
                var ll = circle.getLatLng();
                map_div.fire('click', {
                    latlng: ll,
                    containerPoint: map_div.latLngToContainerPoint(ll),
                    originalEvent: new MouseEvent('click')
                });
            }

            // 십자 핀 자체 드래그 (Leaflet 기본 draggable)
            pin.on('drag', function(e) { circle.setLatLng(e.target.getLatLng()); });
            pin.on('dragend', commit);

            var el = circle.getElement();
            var EDGE_BAND_PX = 12;
            var MIN_R = $min_r, MAX_R = $max_r, STEP_R = 50;
            var dragging = false;

            function circleRadiusPx() {
                var c = circle.getLatLng();
                var east = L.latLng(c.lat, c.lng + circle.getRadius() / (111320 * Math.cos(c.lat * Math.PI / 180)));
                return map_div.latLngToContainerPoint(east).distanceTo(map_div.latLngToContainerPoint(c));
            }
            function zoneOf(ev) {
                var pt = map_div.mouseEventToContainerPoint(ev);
                var cpt = map_div.latLngToContainerPoint(circle.getLatLng());
                var mode = Math.abs(pt.distanceTo(cpt) - circleRadiusPx()) <= EDGE_BAND_PX ? 'resize' : 'move';
                return { mode: mode, pt: pt, cpt: cpt };
            }
            function edgeCursor(pt, cpt) {
                var a = ((Math.atan2(pt.y - cpt.y, pt.x - cpt.x) * 180 / Math.PI) + 360) % 180;
                if (a < 22.5 || a >= 157.5) { return 'ew-resize'; }
                if (a < 67.5) { return 'nwse-resize'; }
                if (a < 112.5) { return 'ns-resize'; }
                return 'nesw-resize';
            }
            el.style.cursor = 'grab';
            el.addEventListener('pointermove', function(me) {
                if (dragging) { return; }
                var z = zoneOf(me);
                el.style.cursor = z.mode === 'resize' ? edgeCursor(z.pt, z.cpt) : 'grab';
            });
            var DOWN = window.PointerEvent ? 'pointerdown' : 'mousedown';
            var MOVE = window.PointerEvent ? 'pointermove' : 'mousemove';
            var UP = window.PointerEvent ? 'pointerup' : 'mouseup';
            el.addEventListener(DOWN, function(de) {
                de.stopPropagation();  // 지도 팬 시작 차단
                de.preventDefault();
                dragging = true;
                var z = zoneOf(de);
                if (z.mode === 'move') { el.style.cursor = 'grabbing'; }
                var startMouse = map_div.mouseEventToLatLng(de);
                var startCenter = circle.getLatLng();
                var moved = false;
                function onMove(me) {
                    moved = true;
                    var ll = map_div.mouseEventToLatLng(me);
                    if (z.mode === 'resize') {
                        var r = Math.max(MIN_R, Math.min(MAX_R, startCenter.distanceTo(ll)));
                        circle.setRadius(r);
                    } else {
                        var nc = L.latLng(
                            startCenter.lat + (ll.lat - startMouse.lat),
                            startCenter.lng + (ll.lng - startMouse.lng)
                        );
                        circle.setLatLng(nc);
                        pin.setLatLng(nc);
                    }
                }
                function onUp() {
                    document.removeEventListener(MOVE, onMove);
                    dragging = false;
                    el.style.cursor = 'grab';
                    if (!moved) { return; }
                    var cont = map_div.getContainer();
                    var swallow = function(ce) {
                        ce.stopPropagation();
                        ce.preventDefault();
                        cont.removeEventListener('click', swallow, true);
                    };
                    cont.addEventListener('click', swallow, true);
                    setTimeout(function() {
                        cont.removeEventListener('click', swallow, true);
                        if (z.mode === 'resize') {
                            var snapped = Math.max(MIN_R, Math.min(MAX_R, Math.round(circle.getRadius() / STEP_R) * STEP_R));
                            circle.setRadius(snapped);
                            pin.setTooltipContent('TURF_RADIUS:' + snapped + ':' + Date.now());
                            pin.fire('click', { latlng: pin.getLatLng() });
                        } else {
                            commit();
                        }
                    }, 60);
                }
                document.addEventListener(MOVE, onMove);
                document.addEventListener(UP, onUp, { once: true });
            });
        }
        turfInitDrag();
    })();
    ">
