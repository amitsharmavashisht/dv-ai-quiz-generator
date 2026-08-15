<?php
/**
 * Plugin Name: DV Digital AI Quiz Generator
 * Description: Turns notes, PDFs, articles and YouTube videos into practice quizzes. Use the [dv_ai_quiz] shortcode.
 * Version:     1.0.0
 * Author:      DV Digital
 * License:     GPL-2.0-or-later
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'DVQ_VERSION', '1.0.0' );
define( 'DVQ_PATH', plugin_dir_path( __FILE__ ) );
define( 'DVQ_URL', plugin_dir_url( __FILE__ ) );

/* -------------------------------------------------------------------------
 * Settings
 * ---------------------------------------------------------------------- */

function dvq_options() {
	return wp_parse_args(
		get_option( 'dvq_settings', array() ),
		array(
			'api_url'    => '',   // e.g. https://dv-quiz.onrender.com
			'shared_key' => '',   // must match APP_SHARED_KEY on the API
		)
	);
}

add_action( 'admin_menu', function () {
	add_options_page(
		'AI Quiz Generator',
		'AI Quiz Generator',
		'manage_options',
		'dvq-settings',
		'dvq_settings_page'
	);
} );

add_action( 'admin_init', function () {
	register_setting( 'dvq_group', 'dvq_settings', function ( $input ) {
		return array(
			'api_url'    => untrailingslashit( esc_url_raw( $input['api_url'] ?? '' ) ),
			'shared_key' => sanitize_text_field( $input['shared_key'] ?? '' ),
		);
	} );
} );

function dvq_settings_page() {
	$o = dvq_options();
	?>
	<div class="wrap">
		<h1>AI Quiz Generator</h1>
		<p>Place the quiz on any page with the shortcode <code>[dv_ai_quiz]</code>.</p>
		<form method="post" action="options.php">
			<?php settings_fields( 'dvq_group' ); ?>
			<table class="form-table">
				<tr>
					<th scope="row"><label for="dvq_api">API address</label></th>
					<td>
						<input id="dvq_api" name="dvq_settings[api_url]" type="url" class="regular-text"
						       value="<?php echo esc_attr( $o['api_url'] ); ?>"
						       placeholder="https://dv-quiz.onrender.com">
						<p class="description">Where the Python service is running. No trailing slash.</p>
					</td>
				</tr>
				<tr>
					<th scope="row"><label for="dvq_key">Shared key</label></th>
					<td>
						<input id="dvq_key" name="dvq_settings[shared_key]" type="text" class="regular-text"
						       value="<?php echo esc_attr( $o['shared_key'] ); ?>">
						<p class="description">Must match <code>APP_SHARED_KEY</code> on the API. Stays on the server.</p>
					</td>
				</tr>
			</table>
			<?php submit_button( 'Save settings' ); ?>
		</form>
	</div>
	<?php
}

/* -------------------------------------------------------------------------
 * Shortcode
 * ---------------------------------------------------------------------- */

add_shortcode( 'dv_ai_quiz', function ( $atts ) {
	$atts = shortcode_atts(
		array(
			'heading' => 'AI Quiz Generator',
			'intro'   => 'Paste your notes or upload a PDF. Get a practice test in seconds.',
		),
		$atts,
		'dv_ai_quiz'
	);

	wp_enqueue_style( 'dvq', DVQ_URL . 'assets/dv-quiz.css', array(), DVQ_VERSION );
	wp_enqueue_script( 'dvq', DVQ_URL . 'assets/dv-quiz.js', array(), DVQ_VERSION, true );
	wp_localize_script( 'dvq', 'DVQ', array(
		'endpoint' => esc_url_raw( rest_url( 'dvq/v1/quiz' ) ),
		'nonce'    => wp_create_nonce( 'wp_rest' ),
		'maxMb'    => 20,
	) );

	ob_start();
	include DVQ_PATH . 'assets/template.php';
	return ob_get_clean();
} );

/* -------------------------------------------------------------------------
 * REST proxy — keeps the shared key server-side and avoids CORS entirely
 * ---------------------------------------------------------------------- */

add_action( 'rest_api_init', function () {
	register_rest_route( 'dvq/v1', '/quiz', array(
		'methods'             => 'POST',
		'callback'            => 'dvq_proxy',
		'permission_callback' => '__return_true',
	) );
} );

function dvq_error( $message, $status = 400 ) {
	return new WP_REST_Response( array( 'error' => $message ), $status );
}

function dvq_proxy( WP_REST_Request $request ) {
	$o = dvq_options();
	if ( empty( $o['api_url'] ) ) {
		return dvq_error( 'The quiz service is not configured yet.', 503 );
	}

	if ( ! wp_verify_nonce( $request->get_header( 'x_wp_nonce' ), 'wp_rest' ) ) {
		return dvq_error( 'Your session expired. Reload the page and try again.', 403 );
	}

	$fields = array(
		'source_type'   => sanitize_text_field( $request->get_param( 'source_type' ) ?? 'text' ),
		'text'          => (string) ( $request->get_param( 'text' ) ?? '' ),
		'url'           => esc_url_raw( $request->get_param( 'url' ) ?? '' ),
		'num_questions' => (int) ( $request->get_param( 'num_questions' ) ?? 10 ),
		'difficulty'    => sanitize_text_field( $request->get_param( 'difficulty' ) ?? 'medium' ),
		'language'      => sanitize_text_field( $request->get_param( 'language' ) ?? 'auto' ),
	);

	$files = $request->get_file_params();
	if ( ! empty( $files['file']['tmp_name'] ) ) {
		if ( $files['file']['size'] > 20 * 1024 * 1024 ) {
			return dvq_error( 'That file is over 20 MB. Upload a smaller one.', 413 );
		}
		$fields['file'] = new CURLFile(
			$files['file']['tmp_name'],
			$files['file']['type'] ?: 'application/octet-stream',
			$files['file']['name']
		);
	}

	$ch = curl_init( $o['api_url'] . '/api/v1/quiz' );
	curl_setopt_array( $ch, array(
		CURLOPT_POST           => true,
		CURLOPT_POSTFIELDS     => $fields,
		CURLOPT_RETURNTRANSFER => true,
		CURLOPT_TIMEOUT        => 120,
		CURLOPT_HTTPHEADER     => array(
			'X-DVQ-Key: ' . $o['shared_key'],
			'Origin: ' . home_url(),
		),
	) );

	$body   = curl_exec( $ch );
	$status = (int) curl_getinfo( $ch, CURLINFO_HTTP_CODE );
	$err    = curl_error( $ch );
	curl_close( $ch );

	if ( $body === false || $status === 0 ) {
		error_log( 'DVQ proxy failure: ' . $err );
		return dvq_error( 'The quiz service did not respond. Try again shortly.', 504 );
	}

	$decoded = json_decode( $body, true );
	if ( ! is_array( $decoded ) ) {
		return dvq_error( 'The quiz service returned an unreadable response.', 502 );
	}

	return new WP_REST_Response( $decoded, $status );
}
