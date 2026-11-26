(function ($) {
    'use strict';
    var form = $('#contact-form');
    var formMessages = $('#form-messages');

    $(form).on('submit', function (e) {
        e.preventDefault();

        var firstName = $(form).find('input[name="first_name"]').val();
        var email = $(form).find('input[name="email"]').val();
        var message = $(form).find('textarea[name="message"]').val();
        var agree = $(form).find('input[name="agree"]').is(':checked');

        // Validation
        if (!firstName || firstName.trim() === '') {
            $(formMessages).removeClass('info-notice').addClass('error').text('Please enter your first name.').slideDown();
            return;
        }

        var emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!email || !emailPattern.test(email.trim())) {
            $(formMessages).removeClass('info-notice').addClass('error').text('Please enter a valid email address.').slideDown();
            return;
        }

        if (!message || message.trim() === '') {
            $(formMessages).removeClass('info-notice').addClass('error').text('Please enter your message.').slideDown();
            return;
        }

        if (!agree) {
            $(formMessages).removeClass('info-notice').addClass('error').text('Please agree to the privacy policy before submitting.').slideDown();
            return;
        }

        // Honest message indicating backend submission status
        $(formMessages).removeClass('error').addClass('info-notice').html(
            '<strong>Notice:</strong> Form submission is not connected to a backend yet. ' +
            'Please email us directly at <a href="mailto:codozent.help@gmail.com" style="text-decoration: underline; font-weight: 600; color: inherit;">codozent.help@gmail.com</a> ' +
            'or call us at <a href="tel:+917680956573" style="text-decoration: underline; font-weight: 600; color: inherit;">+91 7680956573</a>. We look forward to hearing from you!'
        ).slideDown();
    });
})(jQuery);
