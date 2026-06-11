// Vanilla JS for the admin form. No frameworks.
// Handles: live slider readouts, region->district cascade, drag-drop image uploader,
// preview thumbnails, and stepper +/- buttons.

(function () {
    "use strict";

    // ---------- Slider live readout ----------
    document.querySelectorAll("input[type=range].slider").forEach(function (slider) {
        var output = document.getElementById(slider.dataset.output);
        var updateFill = function () {
            var min = Number(slider.min) || 0;
            var max = Number(slider.max) || 100;
            var pct = ((Number(slider.value) - min) / (max - min)) * 100;
            slider.style.setProperty("--fill", pct + "%");
        };
        var updateOutput = function () {
            if (!output) return;
            var v = Number(slider.value);
            output.textContent = v.toLocaleString();
        };
        slider.addEventListener("input", function () {
            updateOutput();
            updateFill();
        });
        updateOutput();
        updateFill();
    });

    // ---------- Stepper +/- ----------
    document.querySelectorAll(".stepper").forEach(function (s) {
        var input = s.querySelector("input");
        var minus = s.querySelector("[data-step='-1']");
        var plus  = s.querySelector("[data-step='+1']");
        var min = Number(input.min);
        var max = Number(input.max);
        var step = Number(input.step) || 1;
        var clamp = function (v) {
            if (!isNaN(min) && v < min) return min;
            if (!isNaN(max) && v > max) return max;
            return v;
        };
        minus && minus.addEventListener("click", function () {
            input.value = clamp((Number(input.value) || 0) - step);
        });
        plus && plus.addEventListener("click", function () {
            input.value = clamp((Number(input.value) || 0) + step);
        });
    });

    // ---------- Region -> District cascade ----------
    var regionInputs = document.querySelectorAll("input[name='region']");
    var districtSelect = document.getElementById("district-select");
    if (regionInputs.length && districtSelect) {
        var DISTRICTS = JSON.parse(districtSelect.dataset.options || "{}");
        var current = districtSelect.value;

        var refresh = function (preserveCurrent) {
            var checked = document.querySelector("input[name='region']:checked");
            if (!checked) return;
            var list = DISTRICTS[checked.value] || [];
            districtSelect.innerHTML = "";
            list.forEach(function (d) {
                var opt = document.createElement("option");
                opt.value = d;
                opt.textContent = d;
                if (preserveCurrent && d === current) opt.selected = true;
                districtSelect.appendChild(opt);
            });
        };

        regionInputs.forEach(function (r) {
            r.addEventListener("change", function () { refresh(false); });
        });
        refresh(true);
    }

    // ---------- Image uploader (drag-drop + click) ----------
    var uploader = document.getElementById("uploader");
    var fileInput = document.getElementById("file-input");
    var previews = document.getElementById("previews");
    var hiddenContainer = document.getElementById("hidden-image-inputs");

    if (uploader && fileInput && previews && hiddenContainer) {
        var uploadUrl = uploader.dataset.uploadUrl;

        var prevent = function (e) { e.preventDefault(); e.stopPropagation(); };
        ["dragenter", "dragover"].forEach(function (ev) {
            uploader.addEventListener(ev, function (e) {
                prevent(e);
                uploader.classList.add("dragover");
            });
        });
        ["dragleave", "drop"].forEach(function (ev) {
            uploader.addEventListener(ev, function (e) {
                prevent(e);
                uploader.classList.remove("dragover");
            });
        });

        uploader.addEventListener("click", function () { fileInput.click(); });
        fileInput.addEventListener("change", function () {
            if (fileInput.files) handleFiles(fileInput.files);
        });
        uploader.addEventListener("drop", function (e) {
            if (e.dataTransfer && e.dataTransfer.files) handleFiles(e.dataTransfer.files);
        });

        function handleFiles(files) {
            Array.prototype.forEach.call(files, function (file) {
                if (!file.type.startsWith("image/")) return;
                uploadOne(file);
            });
        }

        function uploadOne(file) {
            var tile = document.createElement("div");
            tile.className = "preview-tile";
            tile.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:12px;color:#999;">上传中…</div>';
            previews.appendChild(tile);
            updateCoverLabels();

            var fd = new FormData();
            fd.append("file", file);
            fetch(uploadUrl, { method: "POST", body: fd, credentials: "same-origin" })
                .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
                .then(function (res) {
                    if (!res.ok) {
                        tile.innerHTML = '<div style="padding:8px;font-size:12px;color:#cf1322;text-align:center;">' + (res.body.error || "上传失败") + '</div>';
                        return;
                    }
                    renderTile(tile, res.body.url, /*isNew*/ true);
                    addHiddenInput("new_image_urls", res.body.url);
                    updateCoverLabels();
                })
                .catch(function () {
                    tile.innerHTML = '<div style="padding:8px;font-size:12px;color:#cf1322;text-align:center;">上传失败</div>';
                });
        }

        function renderTile(tile, url, isNew) {
            tile.innerHTML = "";
            var img = document.createElement("img");
            img.src = url;
            img.alt = "";
            tile.appendChild(img);

            var remove = document.createElement("div");
            remove.className = "remove-btn";
            remove.title = "删除";
            remove.textContent = "✕";
            remove.addEventListener("click", function (e) {
                e.stopPropagation();
                tile.parentNode.removeChild(tile);
                removeHiddenInput(isNew ? "new_image_urls" : "keep_image_urls", url);
                updateCoverLabels();
            });
            tile.appendChild(remove);
            tile.dataset.url = url;
        }

        function updateCoverLabels() {
            var tiles = previews.querySelectorAll(".preview-tile");
            tiles.forEach(function (t, i) {
                var existing = t.querySelector(".cover-label");
                if (i === 0 && !existing && t.dataset.url) {
                    var label = document.createElement("div");
                    label.className = "cover-label";
                    label.textContent = "封面";
                    t.appendChild(label);
                } else if (i !== 0 && existing) {
                    existing.remove();
                }
            });
        }

        function addHiddenInput(name, value) {
            var input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = value;
            input.dataset.url = value;
            hiddenContainer.appendChild(input);
        }

        function removeHiddenInput(name, value) {
            var sel = hiddenContainer.querySelectorAll('input[name="' + name + '"]');
            sel.forEach(function (el) {
                if (el.value === value) el.parentNode.removeChild(el);
            });
        }

        // Hydrate existing images on edit
        previews.querySelectorAll(".preview-tile[data-existing-url]").forEach(function (tile) {
            var url = tile.dataset.existingUrl;
            renderTile(tile, url, /*isNew*/ false);
            addHiddenInput("keep_image_urls", url);
        });
        updateCoverLabels();
    }
})();
